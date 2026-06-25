"""
Skill Loader — parses SKILL.md frontmatter into SkillDefinition objects.
"""

import re
from pathlib import Path
from typing import Optional

import yaml

from cktclaw.harness.skills.skill_types import SkillDefinition, SkillType, LoadedFrom

_FRONTMATTER_RE = re.compile(r"^---\s*\n(.*?)\n---\s*\n", re.DOTALL)


def parse_skill_md(skill_path: Path, plugin_name: str) -> Optional[SkillDefinition]:
    """Parse a SKILL.md file into a SkillDefinition. Returns None on failure."""
    try:
        text = skill_path.read_text(encoding="utf-8")
        m = _FRONTMATTER_RE.match(text)
        fm = yaml.safe_load(m.group(1)) if m else {}
        if not isinstance(fm, dict):
            fm = {}
        name = fm.get("name") or skill_path.parent.name
        return SkillDefinition(
            name=name,
            skill_type=SkillType.PROMPT,
            loaded_from=LoadedFrom.PLUGIN,
            description=fm.get("description", ""),
            display_name=fm.get("display_name"),
            aliases=fm.get("aliases", []),
            when_to_use=fm.get("when_to_use", ""),
            markdown_content=text,
            skill_root=str(skill_path.parent),
            source=plugin_name,
            user_invocable=True,
        )
    except Exception:
        return None
