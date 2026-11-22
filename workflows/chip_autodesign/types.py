"""Data models for the generic chip AutoDesign flow."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any, Dict, List


@dataclass
class AutoDesignSpec:
    design_kind: str
    module_name: str
    user_task: str
    goal: str
    interfaces: List[Dict[str, str]] = field(default_factory=list)
    protocol: str = "plain RTL"
    clock_reset: str = "single clk, active-low rst_n"
    parameters: Dict[str, Any] = field(default_factory=dict)
    data_widths: Dict[str, int] = field(default_factory=dict)
    ppa_targets: Dict[str, Any] = field(default_factory=dict)
    inference_target: Dict[str, Any] = field(default_factory=dict)
    verification_requirements: List[str] = field(default_factory=list)
    non_goals: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class AutoDesignPlan:
    stages: List[str]
    tools: List[str]
    file_layout: Dict[str, str]
    acceptance_gates: List[str]
    risks: List[str] = field(default_factory=list)
    fallback_strategy: str = "Generate a FixRequest and loop back to RTL or testbench generation."

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class FixRequest:
    failure_type: str
    log_excerpt: str
    suspected_root_cause: str
    target_file: str
    suggested_change: str
    regression_command: str

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class AutoDesignRunResult:
    status: str
    project_dir: str
    spec: AutoDesignSpec
    plan: AutoDesignPlan
    stages: Dict[str, Dict[str, Any]] = field(default_factory=dict)
    artifacts: List[str] = field(default_factory=list)
    qor: Dict[str, Any] = field(default_factory=dict)
    coverage_gaps: List[str] = field(default_factory=list)
    fix_requests: List[FixRequest] = field(default_factory=list)
    summary: str = ""

    def to_dict(self) -> Dict[str, Any]:
        data = asdict(self)
        data["fix_requests"] = [fr.to_dict() for fr in self.fix_requests]
        return data
