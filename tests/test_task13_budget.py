"""Tests for cost & quota governance."""
import pytest


def _bm(per_run=1000, per_day=5000, tmp=None):
    from cktclaw.runtime.budget import BudgetManager
    return BudgetManager(max_per_run=per_run, max_per_day=per_day, store_path=tmp)


def test_under_budget_allows(tmp_path):
    bm = _bm(tmp=tmp_path / "u.json")
    bm.check_and_reserve(500)  # must not raise
    bm.record(500)


def test_per_run_budget_exceeded_raises(tmp_path):
    from cktclaw.runtime.budget import BudgetExceeded
    bm = _bm(per_run=1000, tmp=tmp_path / "u.json")
    bm.record(900)
    with pytest.raises(BudgetExceeded, match="per-run"):
        bm.check_and_reserve(500)


def test_per_day_budget_persists_across_instances(tmp_path):
    from cktclaw.runtime.budget import BudgetExceeded
    store = tmp_path / "u.json"
    _bm(per_day=1000, tmp=store).record(800)
    bm2 = _bm(per_day=1000, tmp=store)
    with pytest.raises(BudgetExceeded, match="per-day"):
        bm2.check_and_reserve(300)


def test_daily_counter_rolls_over(tmp_path, monkeypatch):
    store = tmp_path / "u.json"
    bm = _bm(per_day=1000, tmp=store)
    bm.record(900)
    monkeypatch.setattr(bm, "_today", lambda: "2099-01-02")  # next day
    bm.check_and_reserve(900)  # fresh day, must not raise
