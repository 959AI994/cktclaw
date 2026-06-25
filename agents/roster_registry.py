"""
Agent Roster Registry — static 7-agent definitions + project overrides.

Loads built-in roles from agents/roster/*.md and merges .cktclaw/agents/*.md overrides.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field, asdict
from pathlib import Path
from typing import Any, Dict, List, Literal, Optional

try:
    import yaml
except ImportError:
    yaml = None

ExecutionMode = Literal[
    "coordinator", "worker", "orchestrator_meta", "orchestrator_direct"
]
ModelTier = Literal["orchestrator", "specialist"]

_ROSTER_DIR = Path(__file__).parent / "roster"

# Aliases: file stem / display name -> canonical role_id
_ROLE_ALIASES: Dict[str, str] = {
    "pmagent": "pm_agent",
    "pm_agent": "pm_agent",
    "architectagent": "architect_agent",
    "architect_agent": "architect_agent",
    "edaagent": "eda_agent",
    "eda_agent": "eda_agent",
    "compileragent": "compiler_agent",
    "compiler_agent": "compiler_agent",
    "runtimeagent": "runtime_agent",
    "runtime_agent": "runtime_agent",
    "deployagent": "deploy_agent",
    "deploy_agent": "deploy_agent",
    "optimizeragent": "optimizer_agent",
    "optimizer_agent": "optimizer_agent",
}


@dataclass
class AgentRoleSpec:
    role_id: str
    display_name: str
    system_prompt: str
    description: str = ""
    allowed_tools: List[str] = field(default_factory=list)
    mapped_skills: List[str] = field(default_factory=list)
    execution_mode: ExecutionMode = "worker"
    output_artifacts: List[str] = field(default_factory=list)
    model_tier: ModelTier = "specialist"
    source_path: Optional[str] = None

    def to_dict(self) -> dict:
        return asdict(self)

    def roster_summary_line(self) -> str:
        skills = ", ".join(self.mapped_skills[:4]) or "—"
        return f"- **{self.display_name}** (`{self.role_id}`): {self.description[:120]} | skills: {skills}"


def _parse_list_field(value: Any) -> List[str]:
    if value is None:
        return []
    if isinstance(value, list):
        return [str(v).strip() for v in value if str(v).strip()]
    if isinstance(value, str):
        return [s.strip() for s in value.split(",") if s.strip()]
    return []


def _parse_frontmatter(text: str) -> tuple[dict, str]:
    if not text.startswith("---"):
        return {}, text.strip()
    m = re.match(r"^---\s*\n(.*?)\n---\s*\n?(.*)", text, re.DOTALL)
    if not m:
        return {}, text.strip()
    fm_raw, body = m.group(1), m.group(2).strip()
    if yaml is None:
        return {}, body
    try:
        fm = yaml.safe_load(fm_raw) or {}
    except Exception:
        fm = {}
    if not isinstance(fm, dict):
        fm = {}
    return fm, body


def _normalize_role_id(raw: str) -> str:
    key = raw.strip().lower().replace("-", "_").replace(" ", "_")
    if key in _ROLE_ALIASES:
        return _ROLE_ALIASES[key]
    if not key.endswith("_agent"):
        key = key.replace("agent", "_agent") if "agent" in key else f"{key}_agent"
    return _ROLE_ALIASES.get(key, key)


def _spec_from_markdown(path: Path) -> Optional[AgentRoleSpec]:
    try:
        text = path.read_text(encoding="utf-8")
    except OSError:
        return None
    fm, body = _parse_frontmatter(text)
    role_id = _normalize_role_id(
        fm.get("role_id") or fm.get("name") or path.stem
    )
    return AgentRoleSpec(
        role_id=role_id,
        display_name=str(fm.get("display_name") or fm.get("name") or path.stem),
        description=str(fm.get("description") or fm.get("role") or ""),
        system_prompt=body,
        allowed_tools=_parse_list_field(fm.get("allowed_tools")),
        mapped_skills=_parse_list_field(fm.get("mapped_skills")),
        execution_mode=str(fm.get("execution_mode") or "worker"),  # type: ignore[arg-type]
        output_artifacts=_parse_list_field(fm.get("output_artifacts")),
        model_tier=str(fm.get("model_tier") or "specialist"),  # type: ignore[arg-type]
        source_path=str(path),
    )


class AgentRosterRegistry:
    """Singleton registry of specialist agent role definitions."""

    _instance: Optional["AgentRosterRegistry"] = None

    def __init__(self) -> None:
        self._roles: Dict[str, AgentRoleSpec] = {}
        self._loaded = False

    def load(self, *, extra_dirs: Optional[List[Path]] = None) -> None:
        """Load built-in roster then apply project overrides (later wins)."""
        self._roles.clear()
        if _ROSTER_DIR.is_dir():
            for md in sorted(_ROSTER_DIR.glob("*.md")):
                spec = _spec_from_markdown(md)
                if spec:
                    self._roles[spec.role_id] = spec
        if extra_dirs:
            for d in extra_dirs:
                agents_dir = Path(d) / "agents"
                if not agents_dir.is_dir():
                    continue
                for md in sorted(agents_dir.glob("*.md")):
                    spec = _spec_from_markdown(md)
                    if spec:
                        self._roles[spec.role_id] = spec
        self._loaded = True

    def register_project_agent(self, agent_dict: dict) -> None:
        """Register or override from workspace_parser agent entry."""
        if not self._loaded:
            self.load()
        name = agent_dict.get("name", "")
        role_id = _normalize_role_id(agent_dict.get("role_id") or name)
        existing = self._roles.get(role_id)
        self._roles[role_id] = AgentRoleSpec(
            role_id=role_id,
            display_name=str(agent_dict.get("display_name") or name or role_id),
            description=str(agent_dict.get("description") or ""),
            system_prompt=str(agent_dict.get("system_prompt") or ""),
            allowed_tools=_parse_list_field(agent_dict.get("allowed_tools"))
            or (existing.allowed_tools if existing else []),
            mapped_skills=_parse_list_field(agent_dict.get("mapped_skills"))
            or (existing.mapped_skills if existing else []),
            execution_mode=str(
                agent_dict.get("execution_mode")
                or (existing.execution_mode if existing else "worker")
            ),  # type: ignore[arg-type]
            output_artifacts=_parse_list_field(agent_dict.get("output_artifacts"))
            or (existing.output_artifacts if existing else []),
            model_tier=str(
                agent_dict.get("model_tier")
                or (existing.model_tier if existing else "specialist")
            ),  # type: ignore[arg-type]
            source_path=str(agent_dict.get("source_path") or ""),
        )

    def get(self, role_id: str) -> Optional[AgentRoleSpec]:
        if not self._loaded:
            self.load()
        key = _normalize_role_id(role_id)
        return self._roles.get(key)

    def list_roles(self) -> List[str]:
        if not self._loaded:
            self.load()
        return sorted(self._roles.keys())

    def all_specs(self) -> List[AgentRoleSpec]:
        if not self._loaded:
            self.load()
        return [self._roles[k] for k in sorted(self._roles.keys())]

    def roster_summary(self) -> str:
        lines = ["## CktClaw Seven-Agent Roster", ""]
        for spec in self.all_specs():
            lines.append(spec.roster_summary_line())
        return "\n".join(lines)


def get_roster() -> AgentRosterRegistry:
    if AgentRosterRegistry._instance is None:
        AgentRosterRegistry._instance = AgentRosterRegistry()
        AgentRosterRegistry._instance.load()
    return AgentRosterRegistry._instance


def reset_roster_for_tests() -> None:
    AgentRosterRegistry._instance = None
