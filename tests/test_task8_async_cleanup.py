"""Tests for _run_coro_sync helper in main.py."""
import asyncio
import pytest


def test_run_coro_sync_no_loop():
    from cktclaw.main import _run_coro_sync
    result = []
    async def _coro(): result.append("ran")
    _run_coro_sync(_coro())
    assert result == ["ran"]


def test_run_coro_sync_inside_running_loop():
    from cktclaw.main import _run_coro_sync
    result = []
    async def _coro(): result.append("ran_in_thread")

    async def _driver():
        _run_coro_sync(_coro())

    asyncio.run(_driver())
    assert result == ["ran_in_thread"]


def test_run_coro_sync_propagates_exception():
    from cktclaw.main import _run_coro_sync
    async def _failing(): raise ValueError("intentional")
    with pytest.raises(ValueError, match="intentional"):
        _run_coro_sync(_failing())


def test_run_coro_sync_is_exported():
    import cktclaw.main as m
    assert callable(getattr(m, "_run_coro_sync", None))
