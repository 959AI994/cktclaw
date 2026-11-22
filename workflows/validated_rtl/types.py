"""Types for validated RTL generation workflow."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any, Dict, List, Optional


@dataclass
class HardGateRow:
    gate: str
    status: str
    evidence: str = ""
    note: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class RepairState:
    round_index: int = 0
    max_rounds: int = 5
    last_signature: str = ""
    repeat_count: int = 0
    escalated: bool = False
    signatures: List[str] = field(default_factory=list)

    def record_failure(self, signature: str) -> bool:
        """Record failure signature. Returns True if escalation triggered."""
        self.round_index += 1
        if signature and signature == self.last_signature:
            self.repeat_count += 1
        else:
            self.repeat_count = 1
            self.last_signature = signature
        self.signatures.append(signature)
        if self.repeat_count >= 2:
            self.escalated = True
            return True
        return False

    @property
    def exhausted(self) -> bool:
        return self.round_index >= self.max_rounds or self.escalated


@dataclass
class ValidatedRTLRunResult:
    status: str
    project_dir: str
    module_name: str
    run_id: str
    route_decision: Dict[str, Any] = field(default_factory=dict)
    workflow_status: str = ""
    hard_gates: List[HardGateRow] = field(default_factory=list)
    artifacts: List[str] = field(default_factory=list)
    repair_state: Optional[RepairState] = None
    summary: str = ""
    report_path: str = ""

    def to_dict(self) -> Dict[str, Any]:
        data = asdict(self)
        if self.repair_state is not None:
            data["repair_state"] = asdict(self.repair_state)
        return data
