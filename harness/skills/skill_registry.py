"""
Skill registry — register, discover, and resolve EDA / tool skills.

Responsibilities:
1. register_skill / unregister helpers
2. get_skill / list_skills queries
3. Optional dynamic discovery hooks
4. Conditional activation gates
5. De-duplication and precedence rules

Design:
- One process-wide registry instance
- asyncio.Lock around concurrent registration
- Precedence: bundled < user < project (caller-controlled via override)
- Path-pattern gated skills activate when matching files appear
"""

import asyncio
import os
from typing import Dict, List, Optional, Set, Any
from pathlib import Path

from .skill_types import (
    SkillType,
    SkillDefinition,
    LoadedFrom,
    estimate_skill_frontmatter_tokens,
)


class SkillNotFoundError(Exception):
    """Raised when a skill name or alias cannot be resolved."""
    pass


class SkillRegistry:
    """
    In-memory skill table (singleton).

    Owns registration, lookup, aliases, and conditional activation.
    """

    _instance: Optional['SkillRegistry'] = None
    _lock: asyncio.Lock = asyncio.Lock()

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._skills: Dict[str, SkillDefinition] = {}
            cls._instance._skill_lock = asyncio.Lock()
            cls._instance._aliases: Dict[str, str] = {}  # alias -> skill_name
            cls._instance._conditional_skills: Dict[str, SkillDefinition] = {}
            cls._instance._activated_skill_names: Set[str] = set()
        return cls._instance

    @property
    def skills(self) -> Dict[str, SkillDefinition]:
        """Shallow copy of registered skills (read-only use)."""
        return self._skills.copy()

    async def register_skill(
        self,
        skill: SkillDefinition,
        override: bool = False,
    ) -> None:
        """
        Register a skill definition.

        Args:
            skill: Parsed skill metadata + body.
            override: Replace an existing registration when True.

        Raises:
            ValueError: Name already registered and override is False.
        """
        async with self._skill_lock:
            if skill.name in self._skills and not override:
                raise ValueError(f"Skill '{skill.name}' already registered")

            # Path-gated skills stay dormant until activate_conditional_skills_for_paths
            if skill.paths and len(skill.paths) > 0:
                self._conditional_skills[skill.name] = skill
                return

            self._skills[skill.name] = skill

            for alias in skill.aliases:
                self._aliases[alias] = skill.name

    async def get_skill(self, name_or_alias: str) -> SkillDefinition:
        """
        Resolve a skill by canonical name or alias.

        Args:
            name_or_alias: Primary name or any registered alias.

        Returns:
            A defensive copy of the SkillDefinition.

        Raises:
            SkillNotFoundError: Missing name.
        """
        async with self._skill_lock:
            skill_name = self._aliases.get(name_or_alias, name_or_alias)

            skill = self._skills.get(skill_name)
            if skill is None:
                raise SkillNotFoundError(f"Skill '{name_or_alias}' not found")

            return skill.copy()

    async def list_skills(
        self,
        skill_type: Optional[SkillType] = None,
        loaded_from: Optional[LoadedFrom] = None,
        user_invocable_only: bool = False,
    ) -> List[SkillDefinition]:
        """
        Enumerate registered skills with optional filters.

        Args:
            skill_type: Restrict to a SkillType when set.
            loaded_from: Restrict to a LoadedFrom bucket when set.
            user_invocable_only: Only skills the user may invoke directly.

        Returns:
            Copied definitions (safe to mutate by callers).
        """
        async with self._skill_lock:
            skills = list(self._skills.values())

            if skill_type is not None:
                skills = [s for s in skills if s.skill_type == skill_type]

            if loaded_from is not None:
                skills = [s for s in skills if s.loaded_from == loaded_from]

            if user_invocable_only:
                skills = [s for s in skills if s.user_invocable]

            return [s.copy() for s in skills]

    async def unregister_skill(self, name: str) -> None:
        """
        Remove a skill and scrub its aliases.

        Args:
            name: Canonical skill name.

        Raises:
            SkillNotFoundError: Unknown name.
        """
        async with self._skill_lock:
            if name not in self._skills:
                raise SkillNotFoundError(f"Skill '{name}' not found")

            skill = self._skills[name]

            for alias in skill.aliases:
                if alias in self._aliases:
                    del self._aliases[alias]

            del self._skills[name]

    async def activate_conditional_skills_for_paths(
        self,
        file_paths: List[str],
        cwd: str,
    ) -> List[str]:
        """
        Promote path-gated skills into the active table when patterns match.

        Args:
            file_paths: Files touched or referenced this turn.
            cwd: Anchor for turning absolute paths into project-relative paths.

        Returns:
            Names of skills that transitioned from conditional to active.
        """
        async with self._skill_lock:
            if not self._conditional_skills:
                return []

            activated = []

            for name, skill in list(self._conditional_skills.items()):
                if not skill.paths:
                    continue

                for file_path in file_paths:
                    if os.path.isabs(file_path):
                        rel_path = os.path.relpath(file_path, cwd)
                    else:
                        rel_path = file_path

                    # Lightweight glob match; swap for pathspec if patterns grow complex
                    if self._matches_any_pattern(rel_path, skill.paths):
                        self._skills[name] = skill
                        del self._conditional_skills[name]
                        self._activated_skill_names.add(name)
                        activated.append(name)

                        for alias in skill.aliases:
                            self._aliases[alias] = name

                        break

            return activated

    def _matches_any_pattern(self, path: str, patterns: List[str]) -> bool:
        """
        True when path matches any glob-like pattern.

        Supports * and ** (collapsed to single-star semantics for fnmatch).
        """
        from fnmatch import fnmatch

        for pattern in patterns:
            if "**" in pattern:
                pattern = pattern.replace("**", "*")

            if fnmatch(path, pattern):
                return True

        return False

    async def get_conditional_skill_count(self) -> int:
        """How many skills are still waiting on path matches."""
        async with self._skill_lock:
            return len(self._conditional_skills)

    async def get_stats(self) -> Dict[str, Any]:
        """Aggregate counts for diagnostics / UI."""
        async with self._skill_lock:
            stats = {
                "total_skills": len(self._skills),
                "conditional_skills": len(self._conditional_skills),
                "activated_skills": len(self._activated_skill_names),
                "total_aliases": len(self._aliases),
                "by_type": {},
                "by_source": {},
                "total_tokens": 0,
            }

            for skill in self._skills.values():
                type_key = skill.skill_type if isinstance(skill.skill_type, str) else skill.skill_type.value
                stats["by_type"][type_key] = stats["by_type"].get(type_key, 0) + 1

                source_key = skill.loaded_from if isinstance(skill.loaded_from, str) else skill.loaded_from.value
                stats["by_source"][source_key] = stats["by_source"].get(source_key, 0) + 1

                stats["total_tokens"] += estimate_skill_frontmatter_tokens(skill)

            return stats

    def reset(self) -> None:
        """Clear every table (unit tests only)."""
        self._skills.clear()
        self._aliases.clear()
        self._conditional_skills.clear()
        self._activated_skill_names.clear()


_skill_registry: Optional[SkillRegistry] = None


def get_skill_registry() -> SkillRegistry:
    """Shared SkillRegistry instance."""
    global _skill_registry
    if _skill_registry is None:
        _skill_registry = SkillRegistry()
    return _skill_registry


async def register_skill(skill: SkillDefinition, override: bool = False) -> None:
    """Module-level register_skill."""
    await get_skill_registry().register_skill(skill, override)


async def get_skill(name_or_alias: str) -> SkillDefinition:
    """Module-level get_skill."""
    return await get_skill_registry().get_skill(name_or_alias)


async def list_skills(
    skill_type: Optional[SkillType] = None,
    loaded_from: Optional[LoadedFrom] = None,
    user_invocable_only: bool = False,
) -> List[SkillDefinition]:
    """Module-level list_skills."""
    return await get_skill_registry().list_skills(
        skill_type=skill_type,
        loaded_from=loaded_from,
        user_invocable_only=user_invocable_only,
    )


async def unregister_skill(name: str) -> None:
    """Module-level unregister_skill."""
    await get_skill_registry().unregister_skill(name)


async def activate_conditional_skills_for_paths(
    file_paths: List[str],
    cwd: str,
) -> List[str]:
    """Module-level conditional activation helper."""
    return await get_skill_registry().activate_conditional_skills_for_paths(
        file_paths, cwd
    )
