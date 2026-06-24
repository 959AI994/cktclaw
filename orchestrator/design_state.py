"""
Shared design_state.json — cross-orchestrator blackboard for chip flows.

Persists spec/constraints, fix_requests, QoR snapshots, and history entries
so domain orchestrators and chip-pipeline can coordinate on one design.
"""

from __future__ import annotations

import json
import logging
import os
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Optional

logger = logging.getLogger(__name__)

DEFAULT_FORMAT_VERSION = "1.5"


def _utc_now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def resolve_design_state_path(explicit: Optional[Path] = None) -> Path:
    """
    Resolve where design_state.json should live.

    Priority:
      1. explicit path
      2. CHIP_DESIGN_STATE_PATH env
      3. active RunContext dir / design_state.json
      4. CHIP_DESIGN_MEMORY_ROOT / design_state.json
      5. .cktclaw/design_state.json (cwd)
      6. ~/.cktclaw/design_state.json
    """
    if explicit is not None:
        return explicit

    env_path = os.environ.get("CHIP_DESIGN_STATE_PATH")
    if env_path:
        return Path(env_path).expanduser()

    try:
        from ..runtime.run_context import get_current_run
        run = get_current_run()
        if run is not None:
            return run.dir / "design_state.json"
    except Exception:
        pass

    mem_root = os.environ.get("CHIP_DESIGN_MEMORY_ROOT")
    if mem_root:
        return Path(mem_root).expanduser() / "design_state.json"

    local = Path.cwd() / ".cktclaw" / "design_state.json"
    if local.exists():
        return local

    return Path.home() / ".cktclaw" / "design_state.json"


class DesignStateStore:
    """Read/write helper for design_state.json with atomic persistence."""

    def __init__(self, path: Optional[Path] = None):
        self.path = resolve_design_state_path(path)
        self._data: Dict[str, Any] = {}
        self._loaded = False

    def load(self) -> Dict[str, Any]:
        if self._loaded:
            return self._data
        if self.path.is_file():
            try:
                self._data = json.loads(self.path.read_text(encoding="utf-8"))
            except Exception as e:
                logger.warning("Failed to read %s: %s", self.path, e)
                self._data = {}
        else:
            self._data = {}
        if not self._data:
            self._data = self._empty_state()
        self._loaded = True
        return self._data

    def save(self) -> Path:
        self.load()
        self._data["updated_at"] = _utc_now()
        self.path.parent.mkdir(parents=True, exist_ok=True)
        payload = json.dumps(self._data, ensure_ascii=False, indent=2)
        fd, tmp = tempfile.mkstemp(
            prefix="design_state_", suffix=".json", dir=self.path.parent
        )
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as fh:
                fh.write(payload)
            os.replace(tmp, self.path)
        except Exception:
            try:
                os.unlink(tmp)
            except OSError:
                pass
            raise
        try:
            os.chmod(self.path, 0o600)
        except OSError:
            pass
        return self.path

    def snapshot(self) -> Dict[str, Any]:
        return dict(self.load())

    def merge_stage_qor(
        self,
        orchestrator_name: str,
        stage: str,
        qor: Dict[str, Any],
        status: str,
    ) -> None:
        """Merge stage QoR into design_state under orchestrator/stage keys."""
        data = self.load()
        if not data.get("created_at"):
            data["created_at"] = _utc_now()

        orch_key = orchestrator_name.replace("-orchestrator", "").replace("chip-", "")
        bucket = data.setdefault("orchestrator_qor", {})
        bucket.setdefault(orch_key, {})
        bucket[orch_key][stage] = {
            "status": status,
            "qor": qor,
            "updated_at": _utc_now(),
        }
        self._data = data

    def append_history(
        self,
        agent: str,
        stage: str,
        decision: str,
        reason: str,
        qor: Optional[Dict[str, Any]] = None,
        recommendation: Optional[str] = None,
    ) -> None:
        data = self.load()
        entry: Dict[str, Any] = {
            "timestamp": _utc_now(),
            "agent": agent,
            "stage": stage,
            "decision": decision,
            "confidence": "high",
            "failure_class": "none",
            "retry_strategy": "none",
            "suggested_next_step": recommendation or "proceed",
            "reason": reason,
            "constraint_ref": None,
        }
        if qor:
            entry["qor"] = qor
        hist = data.setdefault("history", [])
        hist.append(entry)
        self._data = data

    def summary_for_prompt(self, max_history: int = 8) -> str:
        """Compact text block for orchestrator prompts."""
        data = self.load()
        lines = ["## Shared Design State (design_state.json)"]

        if data.get("design_name"):
            lines.append(f"- design_name: {data['design_name']}")
        if data.get("constraints"):
            lines.append(f"- constraints keys: {', '.join(data['constraints'].keys())}")

        open_fixes = [
            fr for fr in data.get("fix_requests", [])
            if isinstance(fr, dict) and fr.get("status") == "open"
        ]
        if open_fixes:
            lines.append(f"- open fix_requests: {len(open_fixes)}")
            for fr in open_fixes[:3]:
                lines.append(f"  - {fr.get('id', '?')}: {fr.get('summary', '')[:120]}")

        if data.get("pending_approval"):
            pa = data["pending_approval"]
            lines.append(
                f"- pending_approval: type={pa.get('type')} stage={pa.get('stage')}"
            )

        qor_bucket = data.get("orchestrator_qor", {})
        if qor_bucket:
            lines.append("- recent QoR snapshots:")
            for orch, stages in list(qor_bucket.items())[:4]:
                for st, info in list(stages.items())[-2:]:
                    q = info.get("qor", {}) if isinstance(info, dict) else {}
                    lines.append(f"  - {orch}/{st}: {q}")

        hist = data.get("history", [])
        if hist:
            lines.append("- recent history:")
            for h in hist[-max_history:]:
                if isinstance(h, dict):
                    lines.append(
                        f"  - [{h.get('agent', '?')}] {h.get('stage', '?')}: "
                        f"{h.get('reason', '')[:100]}"
                    )

        lines.append(f"- path: {self.path}")
        return "\n".join(lines)

    @staticmethod
    def _empty_state() -> Dict[str, Any]:
        return {
            "format_version": DEFAULT_FORMAT_VERSION,
            "design_name": None,
            "created_at": None,
            "updated_at": None,
            "cross_domain_iteration_count": 0,
            "pipeline_session_id": None,
            "pipeline_config": {"max_cross_domain_iterations": 3},
            "pending_approval": None,
            "approved_checkpoints": [],
            "constraints": {},
            "spec": {},
            "arch": {},
            "fix_requests": [],
            "archive_fix_requests": [],
            "orchestrator_qor": {},
            "history": [],
            "multi_agent": {
                "session_id": None,
                "current_phase": None,
                "agent_status": {},
                "artifacts_index": {},
                "optimization_round": 0,
            },
        }

    def update_multi_agent_phase(
        self,
        phase: str,
        *,
        session_id: Optional[str] = None,
        agent_status: Optional[Dict[str, str]] = None,
        artifacts_index: Optional[Dict[str, str]] = None,
        optimization_round: Optional[int] = None,
    ) -> None:
        """Update multi-agent blackboard section (backward compatible)."""
        data = self.load()
        ma = data.setdefault("multi_agent", {})
        ma["current_phase"] = phase
        if session_id is not None:
            ma["session_id"] = session_id
        if agent_status:
            status_map = ma.setdefault("agent_status", {})
            status_map.update(agent_status)
        if artifacts_index:
            idx = ma.setdefault("artifacts_index", {})
            idx.update(artifacts_index)
        if optimization_round is not None:
            ma["optimization_round"] = optimization_round
        self._data = data

    def set_spec(self, spec_md: str, *, design_name: Optional[str] = None) -> None:
        data = self.load()
        data["spec"] = {"markdown": spec_md, "updated_at": _utc_now()}
        if design_name:
            data["design_name"] = design_name
        self._data = data

    def set_arch(self, arch_md: str) -> None:
        data = self.load()
        data["arch"] = {"markdown": arch_md, "updated_at": _utc_now()}
        self._data = data

    def add_fix_request(
        self,
        *,
        summary: str,
        detail: str = "",
        source_agent: str = "unknown",
    ) -> str:
        data = self.load()
        fr_id = f"fr-{len(data.get('fix_requests', [])) + 1}"
        entry = {
            "id": fr_id,
            "status": "open",
            "summary": summary,
            "detail": detail,
            "source_agent": source_agent,
            "created_at": _utc_now(),
        }
        data.setdefault("fix_requests", []).append(entry)
        self._data = data
        return fr_id
