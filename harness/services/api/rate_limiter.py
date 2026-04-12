"""
Rate Limiter Service - 速率限制服务

API 服务实现速率限制逻辑。

核心功能：
1. Token bucket 算法
2. 请求速率限制
3. 自动重试延迟
"""

import asyncio
import time
from typing import Optional, Dict, Any
from dataclasses import dataclass, field
from datetime import datetime, timedelta


@dataclass
class RateLimitConfig:
    """速率限制配置"""
    max_requests_per_minute: int = 60
    max_tokens_per_minute: int = 100_000
    max_concurrent_requests: int = 10


@dataclass
class RateLimitState:
    """速率限制状态"""
    requests_count: int = 0
    tokens_count: int = 0
    last_reset_time: float = field(default_factory=time.time)
    concurrent_requests: int = 0


class RateLimiter:
    """
    速率限制器

    使用 Token Bucket 算法实现速率限制
    """

    def __init__(self, config: Optional[RateLimitConfig] = None):
        """
        初始化速率限制器

        Args:
            config: 速率限制配置
        """
        self.config = config or RateLimitConfig()
        self.state = RateLimitState()
        self.lock = asyncio.Lock()
        self.semaphore = asyncio.Semaphore(self.config.max_concurrent_requests)

    async def acquire(self, estimated_tokens: int = 1000) -> bool:
        """
        获取速率限制许可

        Args:
            estimated_tokens: 估算的 Token 数

        Returns:
            是否获取成功
        """
        async with self.lock:
            # 检查是否需要重置计数器
            current_time = time.time()
            if current_time - self.state.last_reset_time >= 60:
                self.state.requests_count = 0
                self.state.tokens_count = 0
                self.state.last_reset_time = current_time

            # 检查请求数限制
            if self.state.requests_count >= self.config.max_requests_per_minute:
                return False

            # 单次请求的估算不应「一口吃掉」整分钟额度，否则首条长上下文会直接失败并触发 ~60s 重试间隔
            est = min(
                max(0, int(estimated_tokens)),
                max(1, self.config.max_tokens_per_minute // 2),
            )
            if self.state.tokens_count + est > self.config.max_tokens_per_minute:
                return False

            # 更新计数器（使用截断后的 est，与上面检查一致）
            self.state.requests_count += 1
            self.state.tokens_count += est

            return True

    async def wait_if_needed(self, estimated_tokens: int = 1000) -> float:
        """
        如果需要，等待直到可以发送请求

        Args:
            estimated_tokens: 估算的 Token 数

        Returns:
            等待时间（秒）
        """
        wait_time = 0.0

        while not await self.acquire(estimated_tokens):
            # 计算需要等待的时间
            async with self.lock:
                time_since_reset = time.time() - self.state.last_reset_time
                time_to_wait = max(0, 60 - time_since_reset)

            if time_to_wait > 0:
                await asyncio.sleep(min(time_to_wait, 1.0))
                wait_time += min(time_to_wait, 1.0)
            else:
                # 重置计数器
                async with self.lock:
                    self.state.requests_count = 0
                    self.state.tokens_count = 0
                    self.state.last_reset_time = time.time()

        return wait_time

    async def execute_with_limit(
        self,
        func,
        estimated_tokens: int = 1000
    ):
        """
        在速率限制下执行函数

        Args:
            func: 要执行的异步函数
            estimated_tokens: 估算的 Token 数

        Returns:
            函数执行结果
        """
        # 等待速率限制
        await self.wait_if_needed(estimated_tokens)

        # 使用信号量限制并发
        async with self.semaphore:
            async with self.lock:
                self.state.concurrent_requests += 1

            try:
                result = await func()
                return result
            finally:
                async with self.lock:
                    self.state.concurrent_requests -= 1

    def get_stats(self) -> Dict[str, Any]:
        """
        获取速率限制统计信息

        Returns:
            统计信息字典
        """
        return {
            "requests_count": self.state.requests_count,
            "tokens_count": self.state.tokens_count,
            "concurrent_requests": self.state.concurrent_requests,
            "max_requests_per_minute": self.config.max_requests_per_minute,
            "max_tokens_per_minute": self.config.max_tokens_per_minute,
            "max_concurrent_requests": self.config.max_concurrent_requests,
            "time_since_reset": time.time() - self.state.last_reset_time,
        }

    def get_wait_time(self) -> float:
        """
        获取需要等待的时间

        Returns:
            等待时间（秒）
        """
        time_since_reset = time.time() - self.state.last_reset_time
        time_to_wait = max(0, 60 - time_since_reset)
        return time_to_wait


# 全局速率限制器实例
_global_rate_limiter: Optional[RateLimiter] = None


def get_rate_limiter(config: Optional[RateLimitConfig] = None) -> RateLimiter:
    """
    获取全局速率限制器实例

    Args:
        config: 速率限制配置

    Returns:
        速率限制器实例
    """
    global _global_rate_limiter

    if _global_rate_limiter is None:
        _global_rate_limiter = RateLimiter(config)

    return _global_rate_limiter
