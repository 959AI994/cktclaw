"""
Cost & quota governance — per-run and per-day token budgets.

Prevents a runaway agent loop from incurring unbounded API spend. The per-run
tally lives on the manager instance (and resets on date rollover); the per-day
tally is persisted to JSON so it survives process restarts.
"""
from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from typing import Dict, Optional


class BudgetExceeded(RuntimeError):
    """Raised when a per-run or per-day token budget would be exceeded."""


class BudgetManager:
    def __init__(self, max_per_run: int = 200_000, max_per_day: int = 2_000_000,
                 store_path: Optional[object] = None, usd_per_1k: float = 0.0):
        self.max_per_run = max_per_run
        self.max_per_day = max_per_day
        self.usd_per_1k = usd_per_1k
        self.store_path = Path(store_path) if store_path else None
        self._run_used = 0
        self._run_day = self._today()

    def _today(self) -> str:
        return datetime.now().strftime("%Y-%m-%d")

    def _sync_day(self) -> None:
        today = self._today()
        if today != self._run_day:
            self._run_day = today
            self._run_used = 0

    def _load_store(self) -> Dict[str, int]:
        if not self.store_path or not self.store_path.is_file():
            return {}
        try:
            data = json.loads(self.store_path.read_text(encoding="utf-8"))
            return data if isinstance(data, dict) else {}
        except Exception:
            return {}

    def _save_store(self, data: Dict[str, int]) -> None:
        if not self.store_path:
            return
        try:
            self.store_path.parent.mkdir(parents=True, exist_ok=True)
            self.store_path.write_text(json.dumps(data), encoding="utf-8")
        except OSError:
            pass

    def _day_used(self) -> int:
        return int(self._load_store().get(self._today(), 0))

    @property
    def run_used(self) -> int:
        self._sync_day()
        return self._run_used

    def check_and_reserve(self, est_tokens: int) -> None:
        """Raise BudgetExceeded if the estimate would breach a budget."""
        self._sync_day()
        if self._run_used + est_tokens > self.max_per_run:
            raise BudgetExceeded(
                f"per-run token budget exceeded: "
                f"{self._run_used} + {est_tokens} > {self.max_per_run}"
            )
        if self._day_used() + est_tokens > self.max_per_day:
            raise BudgetExceeded(
                f"per-day token budget exceeded: "
                f"{self._day_used()} + {est_tokens} > {self.max_per_day}"
            )

    def record(self, actual_tokens: int) -> None:
        """Record actual usage against the per-run and per-day tallies."""
        self._sync_day()
        self._run_used += actual_tokens
        today = self._today()
        data = self._load_store()
        data[today] = int(data.get(today, 0)) + actual_tokens
        self._save_store(data)

        try:
            from .audit import audit_event
            cost = round((actual_tokens / 1000.0) * self.usd_per_1k, 6) if self.usd_per_1k else None
            audit_event(kind="usage", capability="llm", status="ok",
                        tokens=actual_tokens, cost=cost)
        except Exception:
            pass

    def summary(self) -> str:
        self._sync_day()
        return (f"run: {self._run_used}/{self.max_per_run} tokens · "
                f"today: {self._day_used()}/{self.max_per_day} tokens")


_budget_manager: Optional[BudgetManager] = None


def get_budget_manager() -> BudgetManager:
    """Return the process-wide BudgetManager (lazy singleton)."""
    global _budget_manager
    if _budget_manager is None:
        import os
        home = os.environ.get("CKTCLAW_HOME")
        store = Path(home) / "usage.json" if home else Path.cwd() / ".cktclaw" / "usage.json"
        _budget_manager = BudgetManager(store_path=store)
    return _budget_manager
