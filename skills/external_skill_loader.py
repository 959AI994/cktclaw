"""
External Agent Skill discovery — Codex-style SKILL.md search paths.

Scans configured directories for:
  - <root>/SKILL.md          (single-skill repos, e.g. verilog-generator)
  - <root>/*/SKILL.md        (multi-skill bundles)

Configure via ~/.cktclaw/config.yaml ``skills.search_paths`` or
``CKTCLAW_SKILL_PATHS`` (colon-separated absolute paths).
"""

import os
from pathlib import Path
from typing import List, Optional, Set

from cktclaw.harness import SkillDefinition, SkillType, LoadedFrom, register_skill
from cktclaw.plugins.skill_loader import parse_skill_md

from .prompt_skill_utils import make_prompt_executor

# Populated after register_external_skills() for slash-command dispatch
EXTERNAL_PROMPT_SKILL_NAMES: Set[str] = set()


def discover_skill_md_paths(search_roots: List[Path]) -> List[Path]:
    """Return unique SKILL.md paths under each search root."""
    found: List[Path] = []
    seen: Set[str] = set()

    for root in search_roots:
        root = Path(root).expanduser().resolve()
        if not root.is_dir():
            continue

        candidates: List[Path] = []
        root_skill = root / "SKILL.md"
        if root_skill.is_file():
            candidates.append(root_skill)
        candidates.extend(sorted(root.glob("*/SKILL.md")))

        for skill_md in candidates:
            key = str(skill_md)
            if key not in seen:
                seen.add(key)
                found.append(skill_md)

    return found


def get_skill_search_paths() -> List[Path]:
    """Resolve skill search roots from config, env, defaults, and user dir."""
    paths: List[Path] = []

    try:
        from ..config_loader import get_config
        cfg_paths = get_config().get("skills.search_paths", [])
        if isinstance(cfg_paths, list):
            for p in cfg_paths:
                if p:
                    paths.append(Path(str(p)))
    except Exception:
        pass

    env_paths = os.environ.get("CKTCLAW_SKILL_PATHS", "")
    if env_paths:
        for part in env_paths.split(os.pathsep):
            part = part.strip()
            if part:
                paths.append(Path(part))

    user_skills = Path.home() / ".cktclaw" / "skills"
    if user_skills.is_dir():
        paths.append(user_skills)

    # De-dupe while preserving order
    unique: List[Path] = []
    seen: Set[str] = set()
    for p in paths:
        key = str(Path(p).expanduser().resolve())
        if key not in seen:
            seen.add(key)
            unique.append(Path(p))

    return unique


def skill_definition_from_md(skill_path: Path, source: str = "external") -> Optional[SkillDefinition]:
    """Parse SKILL.md and attach a PROMPT executor with skill_root."""
    base = parse_skill_md(skill_path, source)
    if base is None:
        return None

    display = base.user_facing_name()
    base.skill_type = SkillType.PROMPT
    base.loaded_from = LoadedFrom.USER_SETTINGS
    base.user_invocable = True
    base.allowed_tools = ["Read", "Write", "Bash"]
    base.argument_hint = "Natural language RTL/Verilog task for this skill"
    base.argument_names = ["task"]

    if base.name == "erie-verilog-generator":
        return None  # bundled via verilog_generator_skill

    base.executor = make_prompt_executor(skill_path, display)
    return base


async def register_external_skills(verbose: bool = False) -> int:
    """Discover and register external SKILL.md packages. Returns count registered."""
    global EXTERNAL_PROMPT_SKILL_NAMES
    EXTERNAL_PROMPT_SKILL_NAMES = set()

    search_roots = get_skill_search_paths()
    skill_paths = discover_skill_md_paths(search_roots)
    registered = 0

    for skill_md in skill_paths:
        skill_def = skill_definition_from_md(skill_md, source=str(skill_md.parent))
        if skill_def is None:
            if verbose:
                print(f"  ✗ Failed to parse external skill: {skill_md}")
            continue

        try:
            await register_skill(skill_def)
            EXTERNAL_PROMPT_SKILL_NAMES.add(skill_def.name)
            for alias in skill_def.aliases:
                EXTERNAL_PROMPT_SKILL_NAMES.add(alias)
            registered += 1
            if verbose:
                print(f"  ✓ External skill: {skill_def.name} ({skill_md})")
        except ValueError:
            # Already registered (e.g. bundled duplicate name) — skip
            if verbose:
                print(f"  ⊘ Skipped duplicate external skill: {skill_def.name}")
        except Exception as e:
            if verbose:
                print(f"  ✗ External skill registration failed ({skill_md}): {e}")

    return registered
