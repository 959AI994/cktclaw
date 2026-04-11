"""
Error Handler Service - 错误处理服务

错误处理实现。

核心功能：
1. 错误分类和识别
2. 错误恢复策略
3. 错误日志记录
"""

from typing import Optional, Dict, Any, Callable
from dataclasses import dataclass
from enum import Enum
import traceback


class ErrorSeverity(Enum):
    """错误严重程度"""
    INFO = "info"
    WARNING = "warning"
    ERROR = "error"
    CRITICAL = "critical"


@dataclass
class ErrorInfo:
    """错误信息"""
    error_type: str
    message: str
    severity: ErrorSeverity
    recoverable: bool
    details: Optional[Dict[str, Any]] = None
    traceback: Optional[str] = None


class ErrorHandler:
    """
    错误处理器

    统一处理各种错误
    """

    def __init__(self):
        """初始化错误处理器"""
        self.error_counts: Dict[str, int] = {}
        self.error_handlers: Dict[str, Callable] = {}

    def classify_error(self, error: Exception) -> ErrorInfo:
        """
        分类错误

        Args:
            error: 异常对象

        Returns:
            错误信息
        """
        error_str = str(error).lower()
        error_type = type(error).__name__

        # 速率限制错误
        if "rate limit" in error_str or "429" in error_str:
            return ErrorInfo(
                error_type="RateLimitError",
                message=str(error),
                severity=ErrorSeverity.WARNING,
                recoverable=True,
                details={"retry_after": 60}
            )

        # 超时错误
        elif "timeout" in error_str:
            return ErrorInfo(
                error_type="TimeoutError",
                message=str(error),
                severity=ErrorSeverity.WARNING,
                recoverable=True
            )

        # 服务器错误
        elif "500" in error_str or "502" in error_str or "503" in error_str:
            return ErrorInfo(
                error_type="ServerError",
                message=str(error),
                severity=ErrorSeverity.ERROR,
                recoverable=True
            )

        # 客户端错误
        elif "400" in error_str or "401" in error_str or "403" in error_str:
            return ErrorInfo(
                error_type="ClientError",
                message=str(error),
                severity=ErrorSeverity.ERROR,
                recoverable=False
            )

        # Prompt 过长错误
        elif "prompt too long" in error_str or "context length" in error_str:
            return ErrorInfo(
                error_type="PromptTooLongError",
                message=str(error),
                severity=ErrorSeverity.ERROR,
                recoverable=True,
                details={"needs_compaction": True}
            )

        # 网络错误
        elif "connection" in error_str or "network" in error_str:
            return ErrorInfo(
                error_type="NetworkError",
                message=str(error),
                severity=ErrorSeverity.WARNING,
                recoverable=True
            )

        # 未知错误
        else:
            return ErrorInfo(
                error_type=error_type,
                message=str(error),
                severity=ErrorSeverity.ERROR,
                recoverable=False,
                traceback=traceback.format_exc()
            )

    def handle_error(self, error: Exception) -> ErrorInfo:
        """
        处理错误

        Args:
            error: 异常对象

        Returns:
            错误信息
        """
        # 分类错误
        error_info = self.classify_error(error)

        # 更新错误计数
        self.error_counts[error_info.error_type] = \
            self.error_counts.get(error_info.error_type, 0) + 1

        # 调用自定义错误处理器
        handler = self.error_handlers.get(error_info.error_type)
        if handler:
            handler(error_info)

        return error_info

    def register_handler(
        self,
        error_type: str,
        handler: Callable[[ErrorInfo], None]
    ):
        """
        注册错误处理器

        Args:
            error_type: 错误类型
            handler: 处理函数
        """
        self.error_handlers[error_type] = handler

    def get_stats(self) -> Dict[str, Any]:
        """获取错误统计信息"""
        return {
            "error_counts": self.error_counts.copy(),
            "total_errors": sum(self.error_counts.values()),
        }


def is_prompt_too_long_error(error: Exception) -> bool:
    """
    判断是否为 Prompt 过长错误

    Args:
        error: 异常对象

    Returns:
        是否为 Prompt 过长错误
    """
    error_str = str(error).lower()
    return ("prompt too long" in error_str or
            "context length" in error_str or
            "maximum context" in error_str)


def is_rate_limit_error(error: Exception) -> bool:
    """
    判断是否为速率限制错误

    Args:
        error: 异常对象

    Returns:
        是否为速率限制错误
    """
    error_str = str(error).lower()
    return "rate limit" in error_str or "429" in error_str


def is_recoverable_error(error: Exception) -> bool:
    """
    判断错误是否可恢复

    Args:
        error: 异常对象

    Returns:
        是否可恢复
    """
    handler = ErrorHandler()
    error_info = handler.classify_error(error)
    return error_info.recoverable


# 全局错误处理器实例
_global_error_handler: Optional[ErrorHandler] = None


def get_error_handler() -> ErrorHandler:
    """
    获取全局错误处理器实例

    Returns:
        错误处理器实例
    """
    global _global_error_handler

    if _global_error_handler is None:
        _global_error_handler = ErrorHandler()

    return _global_error_handler
