"""Tests for resilience primitives."""
import asyncio
import pytest


def test_with_timeout_raises():
    from cktclaw.runtime.resilience import with_timeout

    async def slow():
        await asyncio.sleep(5)

    async def _run():
        with pytest.raises(asyncio.TimeoutError):
            await with_timeout(slow(), 0.05)

    asyncio.run(_run())


def test_circuit_breaker_opens_after_threshold():
    from cktclaw.runtime.resilience import CircuitBreaker
    cb = CircuitBreaker(fail_threshold=3)
    for _ in range(3):
        cb.record_failure("yosys")
    assert cb.is_open("yosys")


def test_circuit_breaker_isolated_per_tool():
    from cktclaw.runtime.resilience import CircuitBreaker
    cb = CircuitBreaker(fail_threshold=2)
    cb.record_failure("yosys"); cb.record_failure("yosys")
    assert cb.is_open("yosys") and not cb.is_open("abc")


def test_circuit_breaker_resets_on_success():
    from cktclaw.runtime.resilience import CircuitBreaker
    cb = CircuitBreaker(fail_threshold=2)
    cb.record_failure("abc")
    cb.record_success("abc")
    cb.record_failure("abc")
    assert not cb.is_open("abc")


def test_orchestrator_checkpoint_round_trip(tmp_path, monkeypatch):
    monkeypatch.setenv("CKTCLAW_HOME", str(tmp_path))
    from cktclaw.runtime.run_context import new_run
    from cktclaw.orchestrator.engine import save_checkpoint, load_checkpoint
    r = new_run(kind="orchestrator")
    with r.activate():
        save_checkpoint({"stage_index": 2, "completed": ["s0", "s1"]})
        cp = load_checkpoint(r.run_id)
    assert cp["stage_index"] == 2 and cp["completed"] == ["s0", "s1"]
