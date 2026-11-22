"""Pydantic schemas for orchestrator stage results."""
from typing import Any, Dict, List, Literal, Optional
from pydantic import BaseModel, Field, field_validator, model_validator


class StageIssue(BaseModel):
    severity: Literal["PASS", "WARN", "FAIL", "INFO"] = "WARN"
    description: str = ""


class StageResult(BaseModel):
    stage: str = Field(default="")
    status: Literal["PASS", "WARN", "FAIL"] = Field(default="WARN")
    qor: Dict[str, Any] = Field(default_factory=dict)
    issues: List[StageIssue] = Field(default_factory=list)
    recommendation: Optional[str] = Field(default=None)
    raw_response: Optional[str] = Field(default=None)

    @model_validator(mode="before")
    @classmethod
    def normalize_pipeline_fields(cls, data: Any) -> Any:
        """Map pipeline-orchestrator extended fields onto the engine schema."""
        if not isinstance(data, dict):
            return data
        if not data.get("recommendation") and data.get("suggested_next_step"):
            data["recommendation"] = data["suggested_next_step"]
        status = data.get("status")
        if isinstance(status, str):
            normalized = status.upper()
            issue = None
            if normalized in {"OK", "PASSED", "SUCCESS", "COMPLETED"}:
                if normalized == "OK":
                    issue = "Non-standard status OK normalized to PASS."
                normalized = "PASS"
            elif normalized == "WARNING":
                normalized = "WARN"
            elif normalized in {"ERROR", "FAILED", "FAILURE"}:
                normalized = "FAIL"
            elif normalized in {"RUNNING", "PENDING", "IN_PROGRESS"}:
                normalized = "WARN"
                issue = "Non-terminal status was used as final StageResult status."
            data["status"] = normalized
            if issue:
                issues = data.get("issues")
                if not isinstance(issues, list):
                    issues = []
                issues.append({"severity": "WARN", "description": issue})
                data["issues"] = issues
        return data

    @field_validator("qor", mode="before")
    @classmethod
    def coerce_qor_to_dict(cls, v: Any) -> Dict[str, Any]:
        if isinstance(v, dict):
            return v
        return {} if v is None else {"raw": str(v)}

    @field_validator("issues", mode="before")
    @classmethod
    def coerce_issues(cls, v: Any) -> List[Any]:
        if not isinstance(v, list):
            return []
        result = []
        for item in v:
            if isinstance(item, str):
                result.append({"severity": "WARN", "description": item})
            elif isinstance(item, dict):
                result.append(item)
        return result

    def to_engine_dict(self) -> Dict[str, Any]:
        return {
            "stage": self.stage,
            "status": self.status,
            "qor": self.qor,
            "issues": [i.model_dump() for i in self.issues],
            "recommendation": self.recommendation,
            **({"raw_response": self.raw_response} if self.raw_response else {}),
        }


def validate_stage_result(raw: Dict[str, Any], stage: str) -> Dict[str, Any]:
    if not isinstance(raw, dict):
        raise ValueError(f"stage result must be a dict, got {type(raw).__name__}")
    raw.setdefault("stage", stage)
    result = StageResult.model_validate(raw)
    return result.to_engine_dict()
