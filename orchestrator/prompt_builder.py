"""
Prompt Builder — constructs stage-specific LLM message lists for the
orchestrator engine.

Each stage gets:
  - system: SKILL.md content + behaviour rules + available tools
  - user: stage context (name, index, sign-off criteria, previous results, task)
"""

from pathlib import Path
from typing import Optional

from .parser import OrchestratorSpec
from .state_machine import OrchestratorStateMachine
from ..eda_tools.tool_detection import ToolManifest


def build_stage_messages(
    spec: OrchestratorSpec,
    state_machine: OrchestratorStateMachine,
    stage: str,
    user_task: str,
    skill_md: str,
    manifest: Optional[ToolManifest] = None,
    tool_preference: Optional[dict[str, list[str]]] = None,
) -> list[dict[str, str]]:
    """
    Build the messages list to send to the LLM for one stage.

    Args:
        spec: parsed orchestrator specification
        state_machine: current state machine (for context)
        stage: the stage to execute
        user_task: the user's original task description
        skill_md: raw SKILL.md content for this domain
        manifest: detected tools (for available-tool summary)
        tool_preference: per-tool execution preference from MCPServerManager
    """
    system_content = _build_system_prompt(spec, skill_md, manifest, tool_preference)
    user_content = _build_user_prompt(spec, state_machine, stage, user_task)
    return [
        {"role": "system", "content": system_content},
        {"role": "user", "content": user_content},
    ]


def _build_system_prompt(
    spec: OrchestratorSpec,
    skill_md: str,
    manifest: Optional[ToolManifest],
    tool_preference: Optional[dict[str, list[str]]],
) -> str:
    parts: list[str] = []

    parts.append(f"You are the {spec.name} orchestrator.\n")

    if skill_md:
        parts.append("## Domain Skill Reference\n")
        parts.append(skill_md)
        parts.append("")

    if spec.behaviour_rules:
        parts.append("## Behaviour Rules")
        for i, rule in enumerate(spec.behaviour_rules, 1):
            parts.append(f"{i}. {rule}")
        parts.append("")

    if manifest:
        found = [t for t in manifest.found_tools()]
        if found:
            parts.append("## Available Tools on This Host")
            for t in found:
                ver = f" (v{t.version})" if t.version else ""
                parts.append(f"- {t.name}: {t.path}{ver}")
            parts.append("")

    if tool_preference:
        parts.append("## Tool Execution Preference (MCP > Wrapper > Direct)")
        for tool, prefs in tool_preference.items():
            parts.append(f"- {tool}: {' > '.join(prefs)}")
        parts.append("")

    parts.append(
        "## Response Format\n"
        "IMPORTANT: You MUST end your response with EXACTLY this JSON block "
        "(replace values as appropriate):\n"
        "```json\n"
        '{"stage": "<stage_name>", "status": "PASS", "qor": {}, "issues": [], "recommendation": "proceed"}\n'
        "```\n"
        "Rules:\n"
        '- status must be "PASS", "WARN", or "FAIL"\n'
        '- recommendation must be "proceed", "loop_back_to:<stage>", or "escalate"\n'
        "- qor can include numeric metrics like {\"area\": 100, \"delay\": 5.2}\n"
        "- Always include this block even if you have nothing to report — just use the default above.\n"
        "- Do NOT omit this block. It is required for the orchestrator to advance."
    )

    return "\n".join(parts)


def _build_user_prompt(
    spec: OrchestratorSpec,
    state_machine: OrchestratorStateMachine,
    stage: str,
    user_task: str,
) -> str:
    ctx = state_machine.get_stage_context(stage)
    parts: list[str] = []

    parts.append(
        f"## Current Stage: {stage} "
        f"({ctx.get('stage_index', '?')}/{ctx.get('total_stages', '?')})"
    )

    if ctx.get("attempts", 1) > 1:
        parts.append(f"**Attempt #{ctx['attempts']}** (previous attempt failed)")

    parts.append(f"\n### User Task\n{user_task}")

    if spec.sign_off_criteria:
        parts.append("\n### Sign-off Criteria for This Flow")
        for metric, threshold in spec.sign_off_criteria.items():
            parts.append(f"- {metric}: {threshold}")

    rules = ctx.get("applicable_loop_back_rules", [])
    if rules:
        parts.append("\n### Loop-Back Rules Applicable to This Stage")
        for r in rules:
            max_s = f" (max {r['max_iterations']}×)" if r["max_iterations"] != -1 else ""
            parts.append(f"- If {r['condition']} → {r['action']} to {r['target']}{max_s}")

    prev = ctx.get("previous_stage_results", [])
    if prev:
        parts.append("\n### Previous Stage Results")
        for p in prev:
            parts.append(f"- **{p['stage']}**: {p['status']} — QoR: {p.get('qor', {})}")

    stages_remaining = spec.stages[spec.stages.index(stage):]
    parts.append(f"\n### Full Stage Pipeline\n{' → '.join(spec.stages)}")
    parts.append(f"Current position: **{stage}**")

    parts.append(
        "\n\n**IMPORTANT — Tool Budget**: You have at most **8 tool calls** for this stage. "
        "Be efficient: do not repeat the same command, do not run exhaustive sweeps. "
        "Pick the most relevant 1-3 commands, observe the results, then conclude. "
        "Execute this stage now and end your response with the JSON status block."
    )

    return "\n".join(parts)
