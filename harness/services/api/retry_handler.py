"""
Retry Handler Service - 重试处理服务

withRetry 实现重试逻辑。

核心功能：
1. 指数退避重试
2. 错误分类处理
3. 重试次数限制
"""

import asyncio
import time
from typing import Optional, Callable, Awaitable, TypeVar, List, Type
from dataclasses import dataclass
from enum import Enum


T = TypeVar('T')


class ErrorType(Enum):
    """错误类型"""
    RATE_LIMIT = "rate_limit"
    TIMEOUT = "timeout"
    SERVER_ERROR = "server_error"
    CLIENT_ERROR = "client_error"
    NETWORK_ERROR = "network_error"
    UNKNOWN = "unknown"


@dataclass
class RetryConfig:
    """重试配置"""
    max_retries: int = 3
    initial_delay: float = 1.0
    max_delay: float = 60.0
    exponential_base: float = 2.0
    jitter: bool = True


@dataclass
class RetryResult:
    """重试结果"""
    success: bool
    result: Optional[any] = None
    error: Optional[Exception] = None
    attempts: int = 0
    total_delay: float = 0.0


def classify_error(error: Exception) -> ErrorType:
    """
    分类错误类型

    Args:
        error: 异常对象

    Returns:
        错误类型
    """
    error_str = str(error).lower()

    if "rate limit" in error_str or "429" in error_str:
        return ErrorType.RATE_LIMIT
    elif "timeout" in error_str:
        return ErrorType.TIMEOUT
    elif "500" in error_str or "502" in error_str or "503" in error_str:
        return ErrorType.SERVER_ERROR
    elif "400" in error_str or "401" in error_str or "403" in error_str:
        return ErrorType.CLIENT_ERROR
    elif "connection" in error_str or "network" in error_str:
        return ErrorType.NETWORK_ERROR
    else:
        return ErrorType.UNKNOWN


def should_retry(error: Exception, attempt: int, max_retries: int) -> bool:
    """
    判断是否应该重试

    Args:
        error: 异常对象
        attempt: 当前尝试次数
        max_retries: 最大重试次数

    Returns:
        是否应该重试
    """
    if attempt >= max_retries:
        return False

    error_type = classify_error(error)

    # 客户端错误不重试
    if error_type == ErrorType.CLIENT_ERROR:
        return False

    # 其他错误都重试
    return True


def calculate_delay(
    attempt: int,
    config: RetryConfig
) -> float:
    """
    计算重试延迟

    使用指数退避算法

    Args:
        attempt: 当前尝试次数
        config: 重试配置

    Returns:
        延迟时间（秒）
    """
    delay = config.initial_delay * (config.exponential_base ** attempt)
    delay = min(delay, config.max_delay)

    # 添加抖动
    if config.jitter:
        import random
        delay = delay * (0.5 + random.random() * 0.5)

    return delay


async def retry_with_backoff(
    func: Callable[[], Awaitable[T]],
    config: Optional[RetryConfig] = None,
    on_retry: Optional[Callable[[Exception, int, float], None]] = None
) -> T:
    """
    使用指数退避重试执行函数

    Args:
        func: 要执行的异步函数
        config: 重试配置
        on_retry: 重试回调函数

    Returns:
        函数执行结果

    Raises:
        最后一次尝试的异常
    """
    config = config or RetryConfig()
    last_error = None

    for attempt in range(config.max_retries + 1):
        try:
            result = await func()
            return result
        except Exception as e:
            last_error = e

            # 检查是否应该重试
            if not should_retry(e, attempt, config.max_retries):
                raise

            # 计算延迟
            delay = calculate_delay(attempt, config)

            # 调用重试回调
            if on_retry:
                on_retry(e, attempt + 1, delay)

            # 等待后重试
            await asyncio.sleep(delay)

    # 所有重试都失败
    if last_error:
        raise last_error


async def retry_with_fallback(
    primary_func: Callable[[], Awaitable[T]],
    fallback_func: Callable[[], Awaitable[T]],
    config: Optional[RetryConfig] = None
) -> T:
    """
    使用回退策略重试

    先尝试主函数，失败后尝试回退函数

    Args:
        primary_func: 主函数
        fallback_func: 回退函数
        config: 重试配置

    Returns:
        函数执行结果
    """
    try:
        return await retry_with_backoff(primary_func, config)
    except Exception:
        # 主函数失败，尝试回退函数
        return await fallback_func()


class RetryHandler:
    """
    重试处理器

    管理重试逻辑和统计
    """

    def __init__(self, config: Optional[RetryConfig] = None):
        """
        初始化重试处理器

        Args:
            config: 重试配置
        """
        self.config = config or RetryConfig()
        self.total_retries = 0
        self.total_failures = 0
        self.error_counts = {error_type: 0 for error_type in ErrorType}

    async def execute(
        self,
        func: Callable[[], Awaitable[T]],
        on_retry: Optional[Callable[[Exception, int, float], None]] = None
    ) -> RetryResult:
        """
        执行函数并处理重试

        Args:
            func: 要执行的异步函数
            on_retry: 重试回调函数

        Returns:
            重试结果
        """
        attempts = 0
        total_delay = 0.0
        last_error = None

        for attempt in range(self.config.max_retries + 1):
            attempts += 1

            try:
                result = await func()
                return RetryResult(
                    success=True,
                    result=result,
                    attempts=attempts,
                    total_delay=total_delay
                )
            except Exception as e:
                last_error = e
                error_type = classify_error(e)
                self.error_counts[error_type] += 1

                # 检查是否应该重试
                if not should_retry(e, attempt, self.config.max_retries):
                    self.total_failures += 1
                    return RetryResult(
                        success=False,
                        error=e,
                        attempts=attempts,
                        total_delay=total_delay
                    )

                # 计算延迟
                delay = calculate_delay(attempt, self.config)
                total_delay += delay
                self.total_retries += 1

                # 调用重试回调
                if on_retry:
                    on_retry(e, attempt + 1, delay)

                # 等待后重试
                await asyncio.sleep(delay)

        # 所有重试都失败
        self.total_failures += 1
        return RetryResult(
            success=False,
            error=last_error,
            attempts=attempts,
            total_delay=total_delay
        )

    def get_stats(self):
        """获取重试统计信息"""
        return {
            "total_retries": self.total_retries,
            "total_failures": self.total_failures,
            "error_counts": {k.value: v for k, v in self.error_counts.items()},
        }
