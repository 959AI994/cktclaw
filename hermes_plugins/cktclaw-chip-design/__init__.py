"""Hermes registration for the CktClaw chip-design plugin."""

from __future__ import annotations

import logging
import re
from pathlib import Path

from . import schemas, tool_runtime, tools

LOGGER = logging.getLogger(__name__)
PLUGIN_ROOT = Path(__file__).resolve().parent
SKILLS_ROOT = PLUGIN_ROOT / "skills"
_FRONTMATTER_NAME_RE = re.compile(r"^name:\s*([A-Za-z0-9_.-]+)\s*$", re.MULTILINE)


def _skill_name(skill_md: Path) -> str:
    text = skill_md.read_text(encoding="utf-8")
    match = _FRONTMATTER_NAME_RE.search(text)
    if match:
        return match.group(1)
    return "-".join(skill_md.relative_to(SKILLS_ROOT).parts[:-1])


def _discover_skill_files() -> list[tuple[str, Path]]:
    if not SKILLS_ROOT.is_dir():
        return []
    discovered: list[tuple[str, Path]] = []
    for skill_md in sorted(SKILLS_ROOT.glob("*/*/SKILL.md")):
        discovered.append((_skill_name(skill_md), skill_md))
    return discovered


def _register_skills(ctx) -> int:
    count = 0
    for name, skill_md in _discover_skill_files():
        ctx.register_skill(name, skill_md)
        count += 1
    return count


def register(ctx) -> None:
    """Register Hermes-native tools and bundled read-only skills."""
    for tool_spec in schemas.ALL_TOOL_SCHEMAS:
        handler = tools.HANDLERS[tool_spec["name"]]
        ctx.register_tool(
            name=tool_spec["name"],
            toolset="cktclaw_chip_design",
            schema=tool_spec,
            handler=handler,
            description=tool_spec.get("description", ""),
        )

    skill_count = _register_skills(ctx)
    LOGGER.info("cktclaw-chip-design registered %d tools and %d skills", len(schemas.ALL_TOOL_SCHEMAS), skill_count)

    if hasattr(ctx, "register_command"):
        ctx.register_command(
            "cktclaw-chip-doctor",
            lambda raw_args: tools.cktclaw_chip_doctor({"format": "markdown", "raw_args": raw_args}),
            description="Check CktClaw chip toolchain repositories and EDA binaries.",
        )
