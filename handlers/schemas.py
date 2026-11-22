"""Strict schemas for chip intent routing.

The router produces proposals only. Execution authorization belongs to
MissionControl/ToolRunner after policy, file-state, and user-mode checks.
"""

from __future__ import annotations

from typing import Literal, Optional

from pydantic import BaseModel, ConfigDict, Field, model_validator


IntentType = Literal[
    "chip_mission",
    "chip_single_task",
    "chip_artifact_query",
    "chip_qa",
    "normal_chat",
    "clarification",
    "unsafe_or_unsupported",
]

TaskDomain = Literal[
    "rtl_design",
    "verification",
    "simulation",
    "synthesis",
    "formal",
    "sta",
    "hls",
    "physical_design",
    "architecture_exploration",
    "eda_debug",
    "general_chip_qa",
    "artifact_query",
]

RequestedScope = Literal[
    "conceptual_answer",
    "single_step",
    "multi_step_mission",
    "code_modification",
    "tool_execution",
    "artifact_read",
    "unknown",
]

RouterSource = Literal[
    "slash",
    "llm",
    "rules_fallback",
    "cache",
    "safety_gate",
]

FallbackReason = Literal[
    "no_provider",
    "provider_exception",
    "timeout",
    "invalid_json",
    "schema_validation_error",
    "unknown_route",
]


class RouteCandidate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    route: str
    reason: str = ""
    confidence: float = 0.0


class AgentCandidate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str
    reason: str = ""
    available: bool = True


class SkillCandidate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str
    reason: str = ""
    available: bool = True


class ToolCandidate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str
    reason: str
    permission: Literal["proposal_only"] = "proposal_only"
    available: bool
    unsupported_reason: Optional[str] = None
    requires_confirmation: bool = False
    destructive: bool = False


class ArtifactQuery(BaseModel):
    model_config = ConfigDict(extra="forbid")

    kind: Literal["rtl", "simulation_log", "code", "report", "unknown"] = "unknown"
    last_chip_mission_id: Optional[str] = None
    last_project_dir: Optional[str] = None
    candidate_paths: list[str] = Field(default_factory=list)
    resolved_paths: list[str] = Field(default_factory=list)
    missing_artifacts: list[str] = Field(default_factory=list)


class ChipIntent(BaseModel):
    model_config = ConfigDict(extra="forbid")

    is_chip_task: bool
    intent_type: IntentType
    task_domain: Optional[TaskDomain] = None
    requested_scope: RequestedScope = "unknown"

    design_object: Optional[str] = None
    action_verbs: list[str] = Field(default_factory=list)
    deliverables: list[str] = Field(default_factory=list)

    route: str
    confidence: float = 0.0
    router_source: RouterSource
    fallback_reason: Optional[FallbackReason] = None

    rationale: str = ""
    alternatives: list[RouteCandidate] = Field(default_factory=list)
    missing_info: list[str] = Field(default_factory=list)
    needs_clarification: bool = False

    acceptance_gates: list[str] = Field(default_factory=list)

    agent_candidates: list[AgentCandidate] = Field(default_factory=list)
    skill_candidates: list[SkillCandidate] = Field(default_factory=list)
    tool_candidates: list[ToolCandidate] = Field(default_factory=list)

    requires_confirmation: bool = False
    permission_gates: list[str] = Field(default_factory=list)
    unsupported_tools: list[str] = Field(default_factory=list)
    destructive_actions: list[str] = Field(default_factory=list)
    execution_allowed: bool = False

    artifact_query: Optional[ArtifactQuery] = None
    normalized_user_goal: str = ""

    @model_validator(mode="after")
    def validate_fallback_reason(self) -> "ChipIntent":
        if self.router_source != "rules_fallback" and self.fallback_reason is not None:
            raise ValueError("fallback_reason is only valid when router_source='rules_fallback'")
        return self

    def to_dict(self) -> dict:
        return self.model_dump()

    @property
    def is_execution_route(self) -> bool:
        return self.intent_type in {"chip_mission", "chip_single_task"}
