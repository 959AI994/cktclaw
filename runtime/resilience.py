"""
Reliability primitives — timeout, bounded retry, and a per-tool circuit breaker.

Hardens the EDA tool layer: a persistently broken tool trips its breaker and
stops being retried, while transient failures get bounded jittered retries.
"""
from __future__ import annotations

import asyncio
import random
from typing import Awaitable, Callable, Dict, TypeVar

T = TypeVar("T")


async def with_timeout(coro: Awaitable[T], seconds: float) -> T:
    """Await *coro* with a timeout. Raises asyncio.TimeoutError on expiry."""
    return await asyncio.wait_for(coro, timeout=seconds)


class CircuitBreaker:
    """Per-key failure counter. Opens after *fail_threshold* consecutive fails."""

    def __init__(self, fail_threshold: int = 3):
        self.fail_threshold = fail_threshold
        self._failures: Dict[str, int] = {}

    def record_failure(self, key: str) -> None:
        self._failures[key] = self._failures.get(key, 0) + 1

    def record_success(self, key: str) -> None:
        self._failures[key] = 0

    def is_open(self, key: str) -> bool:
        return self._failures.get(key, 0) >= self.fail_threshold

    def reset(self, key: str) -> None:
        self._failures.pop(key, None)


async def retry(
    func: Callable[[], Awaitable[T]],
    attempts: int = 3,
    base_delay: float = 0.2,
    max_delay: float = 5.0,
    exceptions: tuple = (Exception,),
) -> T:
    """Run *func* with bounded retries and jittered exponential backoff."""
    last_exc: BaseException = RuntimeError("retry: no attempts made")
    for attempt in range(attempts):
        try:
            return await func()
        except exceptions as e:  # noqa: B902
            last_exc = e
            if attempt == attempts - 1:
                break
            delay = min(max_delay, base_delay * (2 ** attempt))
            delay += random.uniform(0, base_delay)
            await asyncio.sleep(delay)
    raise last_exc


_circuit_breaker: CircuitBreaker | None = None


def get_circuit_breaker() -> CircuitBreaker:
    """Return the process-wide CircuitBreaker (lazy singleton)."""
    global _circuit_breaker
    if _circuit_breaker is None:
        _circuit_breaker = CircuitBreaker()
    return _circuit_breaker
