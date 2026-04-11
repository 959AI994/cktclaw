"""
API Services - API 服务模块

提供速率限制、重试处理、错误处理等功能。
"""

from .rate_limiter import (
    RateLimitConfig,
    RateLimitState,
    RateLimiter,
    get_rate_limiter,
)

from .retry_handler import (
    ErrorType,
    RetryConfig,
    RetryResult,
    classify_error,
    should_retry,
    calculate_delay,
    retry_with_backoff,
    retry_with_fallback,
    RetryHandler,
)

from .error_handler import (
    ErrorSeverity,
    ErrorInfo,
    ErrorHandler,
    is_prompt_too_long_error,
    is_rate_limit_error,
    is_recoverable_error,
    get_error_handler,
)

__all__ = [
    # Rate Limiter
    "RateLimitConfig",
    "RateLimitState",
    "RateLimiter",
    "get_rate_limiter",

    # Retry Handler
    "ErrorType",
    "RetryConfig",
    "RetryResult",
    "classify_error",
    "should_retry",
    "calculate_delay",
    "retry_with_backoff",
    "retry_with_fallback",
    "RetryHandler",

    # Error Handler
    "ErrorSeverity",
    "ErrorInfo",
    "ErrorHandler",
    "is_prompt_too_long_error",
    "is_rate_limit_error",
    "is_recoverable_error",
    "get_error_handler",
]
