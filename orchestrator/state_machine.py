"""
Orchestrator State Machine — tracks stage progression, enforces loop-back
rules with iteration caps, and checks sign-off criteria.

The state machine is *passive*: it does not execute stages itself. The
engine calls ``start()`` → repeatedly ``complete_stage()`` → checks
``is_finished()``.
"""

from dataclasses import dataclass, field
from typing import Literal, Optional

from .parser import OrchestratorSpec, LoopBackRule


@dataclass
class StageState:
    name: str
    status: Literal["pending", "running", "passed", "failed", "skipped"] = "pending"
    attempts: int = 0
    output: dict = field(default_factory=dict)
    qor: dict = field(default_factory=dict)


@dataclass
class StageTransition:
    action: Literal["proceed", "loop_back", "suspend", "escalate", "finished"]
    next_stage: str = ""
    reason: str = ""
    loop_count: int = 0


class OrchestratorStateMachine:
    """
    Finite state machine over the stage sequence of an orchestrator spec.
    """

    def __init__(self, spec: OrchestratorSpec):
        self.spec = spec
        self._stages: dict[str, StageState] = {
            s: StageState(name=s) for s in spec.stages
        }
        self._stage_order: list[str] = list(spec.stages)
        self._current_idx: int = -1  # not started
        self._loop_counts: dict[str, int] = {}  # "from→target" → count
        self._finished: bool = False

    # ── Properties ────────────────────────────────────────────────────

    @property
    def current_stage(self) -> Optional[str]:
        if self._current_idx < 0 or self._current_idx >= len(self._stage_order):
            return None
        return self._stage_order[self._current_idx]

    @property
    def stages(self) -> dict[str, StageState]:
        return dict(self._stages)

    def is_finished(self) -> bool:
        return self._finished

    # ── Lifecycle ─────────────────────────────────────────────────────

    def start(self) -> str:
        """Begin orchestration at the first stage. Returns stage name."""
        if not self._stage_order:
            self._finished = True
            return ""
        self._current_idx = 0
        stage_name = self._stage_order[0]
        self._stages[stage_name].status = "running"
        self._stages[stage_name].attempts += 1
        return stage_name

    def complete_stage(
        self, stage: str, status: str, qor: Optional[dict] = None,
        recommendation: Optional[str] = None,
    ) -> StageTransition:
        """
        Record stage outcome and determine the next transition.

        Args:
            stage: stage name that just completed
            status: "PASS", "FAIL", or "WARN"
            qor: quality-of-results dict (metrics) from the stage
            recommendation: optional LLM recommendation (e.g. loop_back_to:rtl_coding)
        """
        if stage not in self._stages:
            return StageTransition(action="escalate", reason=f"Unknown stage: {stage}")

        ss = self._stages[stage]
        ss.qor = qor or {}

        normalized = status.upper()
        if normalized == "PASS":
            ss.status = "passed"
            loop_target = self._parse_loop_back_target(recommendation)
            if loop_target:
                return self._jump_to_stage(
                    loop_target,
                    reason=f"LLM recommendation: {recommendation}",
                )
            return self._advance()
        if normalized == "WARN":
            ss.status = "skipped"
            loop_target = self._parse_loop_back_target(recommendation)
            if loop_target:
                return self._jump_to_stage(
                    loop_target,
                    reason=f"LLM recommendation: {recommendation}",
                )
            return self._advance()

        # status == FAIL
        ss.status = "failed"
        return self._handle_failure(stage)

    # ── Internal ──────────────────────────────────────────────────────

    def _parse_loop_back_target(self, recommendation: Optional[str]) -> Optional[str]:
        """Parse loop_back_to:<stage> from an LLM recommendation string."""
        if not recommendation or not isinstance(recommendation, str):
            return None
        rec = recommendation.strip()
        if rec.startswith("loop_back_to:"):
            target = rec.split(":", 1)[1].strip()
            if target in self._stages:
                return target
        return None

    def _jump_to_stage(self, target: str, reason: str) -> StageTransition:
        """Jump to a prior stage (LLM-driven loop-back)."""
        if target not in self._stages:
            return StageTransition(
                action="escalate",
                reason=f"Loop-back target '{target}' not in pipeline",
            )
        target_idx = self._stage_order.index(target)
        self._current_idx = target_idx
        self._stages[target].status = "running"
        self._stages[target].attempts += 1
        loop_key = f"recommendation→{target}"
        count = self._loop_counts.get(loop_key, 0) + 1
        self._loop_counts[loop_key] = count
        if count > 5:
            return StageTransition(
                action="escalate",
                reason=f"Max recommendation loop-backs to '{target}' exceeded",
                loop_count=count,
            )
        return StageTransition(
            action="loop_back",
            next_stage=target,
            reason=reason,
            loop_count=count,
        )

    def _advance(self) -> StageTransition:
        """Move to the next stage in sequence, or finish."""
        next_idx = self._current_idx + 1
        if next_idx >= len(self._stage_order):
            self._finished = True
            return StageTransition(action="finished", reason="All stages complete")

        self._current_idx = next_idx
        next_stage = self._stage_order[next_idx]
        self._stages[next_stage].status = "running"
        self._stages[next_stage].attempts += 1
        return StageTransition(action="proceed", next_stage=next_stage)

    def _handle_failure(self, failed_stage: str) -> StageTransition:
        """Evaluate loop-back rules for the failed stage."""
        for rule in self.spec.loop_back_rules:
            if not self._rule_matches_stage(rule, failed_stage):
                continue

            if rule.action in ("suspend", "escalate"):
                return StageTransition(
                    action=rule.action,
                    reason=rule.condition,
                )

            # loop_back
            loop_key = f"{failed_stage}→{rule.target_stage}"
            current_count = self._loop_counts.get(loop_key, 0)

            if rule.max_iterations != -1 and current_count >= rule.max_iterations:
                return StageTransition(
                    action="escalate",
                    reason=f"Max loop-back iterations ({rule.max_iterations}) "
                           f"exceeded for {loop_key}",
                    loop_count=current_count,
                )

            self._loop_counts[loop_key] = current_count + 1
            target = rule.target_stage
            if target in self._stages:
                target_idx = self._stage_order.index(target)
                self._current_idx = target_idx
                self._stages[target].status = "running"
                self._stages[target].attempts += 1
                return StageTransition(
                    action="loop_back",
                    next_stage=target,
                    reason=rule.condition,
                    loop_count=current_count + 1,
                )

        # No matching rule → escalate by default
        return StageTransition(
            action="escalate",
            reason=f"Stage '{failed_stage}' failed with no matching loop-back rule",
        )

    def _rule_matches_stage(self, rule: LoopBackRule, stage: str) -> bool:
        """Check whether a loop-back rule applies to *stage*."""
        if rule.from_stage and rule.from_stage == stage:
            return True
        if not rule.from_stage and stage in rule.condition:
            return True
        return False

    # ── Context for prompt builder ────────────────────────────────────

    def get_stage_context(self, stage: str) -> dict:
        """Return context dict for the prompt builder."""
        ss = self._stages.get(stage)
        if not ss:
            return {}

        prev_results: list[dict] = []
        for s in self._stage_order:
            if s == stage:
                break
            prev_ss = self._stages[s]
            if prev_ss.status == "passed":
                prev_results.append({
                    "stage": s, "status": prev_ss.status, "qor": prev_ss.qor,
                })

        applicable_rules = [
            {
                "condition": r.condition,
                "target": r.target_stage,
                "max_iterations": r.max_iterations,
                "action": r.action,
            }
            for r in self.spec.loop_back_rules
            if self._rule_matches_stage(r, stage)
        ]

        return {
            "stage_name": stage,
            "stage_index": self._stage_order.index(stage) + 1,
            "total_stages": len(self._stage_order),
            "attempts": ss.attempts,
            "sign_off_criteria": self.spec.sign_off_criteria,
            "applicable_loop_back_rules": applicable_rules,
            "previous_stage_results": prev_results,
        }

    def get_state_snapshot(self) -> dict:
        """Full state for persistence or display."""
        return {
            "current_stage": self.current_stage,
            "current_idx": self._current_idx,
            "finished": self._finished,
            "stage_order": list(self._stage_order),
            "stages": {
                name: {
                    "status": ss.status,
                    "attempts": ss.attempts,
                    "qor": ss.qor,
                }
                for name, ss in self._stages.items()
            },
            "loop_counts": dict(self._loop_counts),
        }

    def restore_from_snapshot(self, snapshot: dict) -> Optional[str]:
        """
        Restore internal state from a checkpoint snapshot.

        Returns the stage name to resume from, or None if restoration failed.
        """
        if not snapshot:
            return None
        stage_order = snapshot.get("stage_order")
        if stage_order and stage_order != self._stage_order:
            logger_msg = "Checkpoint stage_order mismatch — ignoring restore"
            import logging
            logging.getLogger(__name__).warning(logger_msg)

        stages_data = snapshot.get("stages", {})
        for name, info in stages_data.items():
            if name in self._stages and isinstance(info, dict):
                ss = self._stages[name]
                ss.status = info.get("status", ss.status)
                ss.attempts = info.get("attempts", ss.attempts)
                ss.qor = info.get("qor", {}) or {}

        self._loop_counts = dict(snapshot.get("loop_counts", {}))
        self._finished = bool(snapshot.get("finished", False))
        self._current_idx = snapshot.get("current_idx", -1)

        if self._finished:
            return None

        stage = self.current_stage
        if stage and stage in self._stages:
            self._stages[stage].status = "running"
            return stage

        # Fall back to first incomplete stage
        for name in self._stage_order:
            if self._stages[name].status in ("pending", "failed"):
                self._current_idx = self._stage_order.index(name)
                self._stages[name].status = "running"
                self._stages[name].attempts += 1
                self._finished = False
                return name
        return None
