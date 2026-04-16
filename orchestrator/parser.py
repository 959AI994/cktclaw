"""
Orchestrator Markdown Parser — extracts a structured OrchestratorSpec from
the ``*-orchestrator.md`` files in digital-chip-design-agents.

Parsing strategy:
  1. YAML frontmatter  → name, description, model, maxTurns, skills
  2. ``## Stage Sequence``  → ordered stage list (split on `` → ``)
  3. ``## Loop-Back Rules``  → list of LoopBackRule
  4. ``## Sign-off Criteria``  → metric → threshold mapping
  5. ``## Tool Options``  → open-source / proprietary tool lists
  6. ``### MCP Preference``  → ordered preference list
  7. ``## Behaviour Rules``  → numbered rule strings
"""

import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional


@dataclass
class LoopBackRule:
    from_stage: str
    condition: str
    target_stage: str
    max_iterations: int = -1  # -1 = unlimited
    action: str = "loop_back"  # loop_back | suspend | escalate


@dataclass
class OrchestratorSpec:
    name: str = ""
    description: str = ""
    model: str = "sonnet"
    max_turns: int = 40
    skills: list[str] = field(default_factory=list)
    stages: list[str] = field(default_factory=list)
    tool_options: dict[str, list[str]] = field(default_factory=dict)
    mcp_preference: list[str] = field(default_factory=list)
    loop_back_rules: list[LoopBackRule] = field(default_factory=list)
    sign_off_criteria: dict[str, str] = field(default_factory=dict)
    behaviour_rules: list[str] = field(default_factory=list)
    raw_text: str = ""


# ── Section extraction helpers ────────────────────────────────────────

def _extract_frontmatter(text: str) -> dict:
    """Parse YAML frontmatter between ``---`` fences."""
    m = re.match(r"^---\s*\n(.*?)\n---", text, re.DOTALL)
    if not m:
        return {}
    try:
        import yaml
        return yaml.safe_load(m.group(1)) or {}
    except Exception:
        # Fallback: line-by-line key: value
        result: dict = {}
        for line in m.group(1).splitlines():
            if ":" in line:
                k, _, v = line.partition(":")
                result[k.strip()] = v.strip()
        return result


def _section_text(text: str, heading: str) -> str:
    """Return the body text under ``## heading`` up to the next ``## ``."""
    pattern = re.compile(
        rf"^##\s+{re.escape(heading)}\s*$\n(.*?)(?=^##\s|\Z)",
        re.MULTILINE | re.DOTALL,
    )
    m = pattern.search(text)
    return m.group(1).strip() if m else ""


def _subsection_text(text: str, heading: str) -> str:
    """Return the body text under ``### heading``."""
    pattern = re.compile(
        rf"^###\s+{re.escape(heading)}\s*$\n(.*?)(?=^###?\s|\Z)",
        re.MULTILINE | re.DOTALL,
    )
    m = pattern.search(text)
    return m.group(1).strip() if m else ""


# ── Individual parsers ────────────────────────────────────────────────

def _parse_stages(text: str) -> list[str]:
    body = _section_text(text, "Stage Sequence")
    if not body:
        return []
    line = body.splitlines()[0].strip()
    return [s.strip() for s in line.split("→") if s.strip()]


def _parse_tool_options(text: str) -> dict[str, list[str]]:
    section = _section_text(text, "Tool Options")
    if not section:
        return {}
    result: dict[str, list[str]] = {}
    for category_heading in ("Open-Source", "Proprietary"):
        sub = _subsection_text(section, category_heading)
        if not sub:
            sub = _subsection_text(text, category_heading)
        tools: list[str] = []
        for line in sub.splitlines():
            line = line.strip()
            if line.startswith("-"):
                backtick_m = re.search(r"`(\w[\w-]*)`", line)
                if backtick_m:
                    tools.append(backtick_m.group(1))
        key = "open_source" if "Open" in category_heading else "proprietary"
        if tools:
            result[key] = tools
    return result


def _parse_mcp_preference(text: str) -> list[str]:
    sub = _subsection_text(text, "MCP Preference")
    if not sub:
        return []
    prefs: list[str] = []
    for line in sub.splitlines():
        line = line.strip()
        m = re.match(r"^\d+\.\s+\*\*(.+?)\*\*", line)
        if m:
            prefs.append(m.group(1).strip())
    return prefs


def _parse_loop_back_rules(text: str, stages: list[str]) -> list[LoopBackRule]:
    section = _section_text(text, "Loop-Back Rules")
    if not section:
        return []

    rules: list[LoopBackRule] = []
    for line in section.splitlines():
        line = line.strip()
        if not line.startswith("-"):
            continue
        line = line.lstrip("- ").strip()

        # Detect action type
        action = "loop_back"
        if "SUSPEND" in line.upper():
            action = "suspend"
        elif "escalate" in line.lower():
            action = "escalate"

        # Extract target stage from ``→ target_stage``
        arrow_m = re.search(r"→\s*(\w[\w_]*)", line)
        target = arrow_m.group(1) if arrow_m else ""

        # Extract max iterations from ``(max N×)``
        max_m = re.search(r"\(max\s+(\d+)", line)
        unlimited_m = re.search(r"\(unlimited\)", line, re.IGNORECASE)
        max_iter = int(max_m.group(1)) if max_m else (-1 if unlimited_m else 3)

        # Infer from_stage: the first stage name mentioned before ``→``
        from_stage = ""
        before_arrow = line.split("→")[0] if "→" in line else line
        for s in stages:
            if s in before_arrow:
                from_stage = s
                break

        # Full condition text is the part before ``→``
        condition = before_arrow.strip().rstrip("→").strip()

        rules.append(LoopBackRule(
            from_stage=from_stage,
            condition=condition,
            target_stage=target,
            max_iterations=max_iter,
            action=action,
        ))

    return rules


def _parse_sign_off_criteria(text: str) -> dict[str, str]:
    section = _section_text(text, "Sign-off Criteria")
    if not section:
        # Try alternate heading
        section = _section_text(text, "Sign-off Criteria (all required)")
    if not section:
        return {}
    criteria: dict[str, str] = {}
    for line in section.splitlines():
        line = line.strip().lstrip("- ").strip()
        if ":" in line:
            k, _, v = line.partition(":")
            k = k.strip()
            v = v.strip()
            if k and v:
                criteria[k] = v
    return criteria


def _parse_behaviour_rules(text: str) -> list[str]:
    section = _section_text(text, "Behaviour Rules")
    if not section:
        return []
    rules: list[str] = []
    for line in section.splitlines():
        line = line.strip()
        m = re.match(r"^\d+\.\s+(.+)", line)
        if m:
            rules.append(m.group(1).strip())
    return rules


# ── Public API ────────────────────────────────────────────────────────

def parse_orchestrator(path_or_text: str | Path) -> OrchestratorSpec:
    """
    Parse an orchestrator markdown file (or raw text) into an OrchestratorSpec.

    Args:
        path_or_text: file path (Path or str ending in .md) or raw markdown string
    """
    if isinstance(path_or_text, Path) or (
        isinstance(path_or_text, str) and path_or_text.endswith(".md")
    ):
        text = Path(path_or_text).read_text()
    else:
        text = path_or_text

    fm = _extract_frontmatter(text)
    stages = _parse_stages(text)
    skills_raw = fm.get("skills", [])
    if isinstance(skills_raw, str):
        skills_raw = [skills_raw]

    return OrchestratorSpec(
        name=fm.get("name", ""),
        description=fm.get("description", ""),
        model=fm.get("model", "sonnet"),
        max_turns=int(fm.get("maxTurns", 40)),
        skills=skills_raw,
        stages=stages,
        tool_options=_parse_tool_options(text),
        mcp_preference=_parse_mcp_preference(text),
        loop_back_rules=_parse_loop_back_rules(text, stages),
        sign_off_criteria=_parse_sign_off_criteria(text),
        behaviour_rules=_parse_behaviour_rules(text),
        raw_text=text,
    )
