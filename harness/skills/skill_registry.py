"""
Skill Registry - 技能注册与管理

参考 src/skills/bundledSkills.ts 和 loadSkillsDir.ts 实现 Python 版本的技能注册系统。

核心职责：
1. 技能注册（register_skill）
2. 技能查询（get_skill, list_skills）
3. 技能发现（动态加载）
4. 技能激活（条件激活）
5. 去重与优先级管理

设计原则：
- 单例模式（全局注册表）
- 线程安全（asyncio.Lock）
- 优先级管理（bundled < user < project）
- 条件激活（基于路径模式）
"""

import asyncio
import os
from typing import Dict, List, Optional, Set
from pathlib import Path

from .skill_types import (
    SkillType,
    SkillDefinition,
    LoadedFrom,
    estimate_skill_frontmatter_tokens,
)


class SkillNotFoundError(Exception):
    """技能不存在错误"""
    pass


class SkillRegistry:
    """
    技能注册表（单例模式）

    管理所有技能的注册、查询、激活
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
        """获取所有技能（只读）"""
        return self._skills.copy()

    async def register_skill(
        self,
        skill: SkillDefinition,
        override: bool = False,
    ) -> None:
        """
        注册技能

        Args:
            skill: 技能定义
            override: 是否覆盖已存在的技能

        Raises:
            ValueError: 技能已存在且 override=False
        """
        async with self._skill_lock:
            # 检查是否已存在
            if skill.name in self._skills and not override:
                raise ValueError(f"Skill '{skill.name}' already registered")

            # 条件技能（有路径过滤）
            if skill.paths and len(skill.paths) > 0:
                self._conditional_skills[skill.name] = skill
                return

            # 注册技能
            self._skills[skill.name] = skill

            # 注册别名
            for alias in skill.aliases:
                self._aliases[alias] = skill.name

    async def get_skill(self, name_or_alias: str) -> SkillDefinition:
        """
        获取技能

        Args:
            name_or_alias: 技能名称或别名

        Returns:
            技能定义

        Raises:
            SkillNotFoundError: 技能不存在
        """
        async with self._skill_lock:
            # 尝试别名
            skill_name = self._aliases.get(name_or_alias, name_or_alias)

            # 查找技能
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
        列出技能

        Args:
            skill_type: 过滤技能类型（可选）
            loaded_from: 过滤来源（可选）
            user_invocable_only: 仅返回用户可调用的技能

        Returns:
            技能列表
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
        注销技能

        Args:
            name: 技能名称

        Raises:
            SkillNotFoundError: 技能不存在
        """
        async with self._skill_lock:
            if name not in self._skills:
                raise SkillNotFoundError(f"Skill '{name}' not found")

            skill = self._skills[name]

            # 删除别名
            for alias in skill.aliases:
                if alias in self._aliases:
                    del self._aliases[alias]

            # 删除技能
            del self._skills[name]

    async def activate_conditional_skills_for_paths(
        self,
        file_paths: List[str],
        cwd: str,
    ) -> List[str]:
        """
        激活条件技能（基于路径模式）

        Args:
            file_paths: 文件路径列表
            cwd: 当前工作目录

        Returns:
            激活的技能名称列表
        """
        async with self._skill_lock:
            if not self._conditional_skills:
                return []

            activated = []

            for name, skill in list(self._conditional_skills.items()):
                if not skill.paths:
                    continue

                # 检查是否匹配路径模式
                for file_path in file_paths:
                    # 转换为相对路径
                    if os.path.isabs(file_path):
                        rel_path = os.path.relpath(file_path, cwd)
                    else:
                        rel_path = file_path

                    # 简单的通配符匹配（可以使用 pathspec 库实现更复杂的匹配）
                    if self._matches_any_pattern(rel_path, skill.paths):
                        # 激活技能
                        self._skills[name] = skill
                        del self._conditional_skills[name]
                        self._activated_skill_names.add(name)
                        activated.append(name)

                        # 注册别名
                        for alias in skill.aliases:
                            self._aliases[alias] = name

                        break

            return activated

    def _matches_any_pattern(self, path: str, patterns: List[str]) -> bool:
        """
        检查路径是否匹配任意模式

        简单实现：支持 * 和 ** 通配符
        """
        from fnmatch import fnmatch

        for pattern in patterns:
            # ** 匹配任意层级
            if "**" in pattern:
                pattern = pattern.replace("**", "*")

            if fnmatch(path, pattern):
                return True

        return False

    async def get_conditional_skill_count(self) -> int:
        """获取待激活的条件技能数量"""
        async with self._skill_lock:
            return len(self._conditional_skills)

    async def get_stats(self) -> Dict[str, any]:
        """
        获取技能统计信息

        Returns:
            统计信息字典
        """
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
                # 按类型统计
                type_key = skill.skill_type if isinstance(skill.skill_type, str) else skill.skill_type.value
                stats["by_type"][type_key] = stats["by_type"].get(type_key, 0) + 1

                # 按来源统计
                source_key = skill.loaded_from if isinstance(skill.loaded_from, str) else skill.loaded_from.value
                stats["by_source"][source_key] = stats["by_source"].get(source_key, 0) + 1

                # Token 估算
                stats["total_tokens"] += estimate_skill_frontmatter_tokens(skill)

            return stats

    def reset(self) -> None:
        """重置技能注册表（仅用于测试）"""
        self._skills.clear()
        self._aliases.clear()
        self._conditional_skills.clear()
        self._activated_skill_names.clear()


# 全局单例
_skill_registry: Optional[SkillRegistry] = None


def get_skill_registry() -> SkillRegistry:
    """获取全局技能注册表单例"""
    global _skill_registry
    if _skill_registry is None:
        _skill_registry = SkillRegistry()
    return _skill_registry


# 便捷函数
async def register_skill(skill: SkillDefinition, override: bool = False) -> None:
    """注册技能"""
    await get_skill_registry().register_skill(skill, override)


async def get_skill(name_or_alias: str) -> SkillDefinition:
    """获取技能"""
    return await get_skill_registry().get_skill(name_or_alias)


async def list_skills(
    skill_type: Optional[SkillType] = None,
    loaded_from: Optional[LoadedFrom] = None,
    user_invocable_only: bool = False,
) -> List[SkillDefinition]:
    """列出技能"""
    return await get_skill_registry().list_skills(
        skill_type=skill_type,
        loaded_from=loaded_from,
        user_invocable_only=user_invocable_only,
    )


async def unregister_skill(name: str) -> None:
    """注销技能"""
    await get_skill_registry().unregister_skill(name)


async def activate_conditional_skills_for_paths(
    file_paths: List[str],
    cwd: str,
) -> List[str]:
    """激活条件技能"""
    return await get_skill_registry().activate_conditional_skills_for_paths(
        file_paths, cwd
    )
