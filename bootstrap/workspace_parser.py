"""
Workspace Parser - Project Behavior Layer for CktClaw

Sidecar loader that discovers and loads `.cktclaw/` directories:
- CKTCLAW.md: Project constitution → injected into CktMem PROJECT layer
- skills/: Custom skills → auto-registered to SkillRegistry
- agents/: Specialized agents → registered to CoordinatorManager

Design principles (from Claude Code's .claude/ pattern):
- Hierarchical discovery: CWD → git root
- YAML frontmatter parsing for skill/agent metadata
- Conditional activation via path globs
- Graceful degradation: no .cktclaw/ = silent skip
"""

import os
import asyncio
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple
from dataclasses import dataclass, field

try:
    import yaml
except ImportError:
    yaml = None


# ━━━━━━━━━━ Data Models ━━━━━━━━━━

@dataclass
class ProjectBehavior:
    """Parsed project behavior configuration."""

    constitution: Optional[str] = None
    constitution_path: Optional[str] = None
    skills: List[Dict[str, Any]] = field(default_factory=list)
    agents: List[Dict[str, Any]] = field(default_factory=list)
    project_root: Optional[str] = None

    @property
    def has_content(self) -> bool:
        return bool(self.constitution or self.skills or self.agents)


# ━━━━━━━━━━ Core Parser ━━━━━━━━━━

class WorkspaceParser:
    """
    Discovers and parses `.cktclaw/` directories in the project workspace.

    Directory layout:
        .cktclaw/
            CKTCLAW.md              # Project constitution
            skills/                 # Custom skills
                my_skill/
                    SKILL.md        # Frontmatter + markdown
            agents/                 # Specialized agents
                timing_expert.md    # Frontmatter + system prompt
    """

    CKTCLAW_DIR = ".cktclaw"
    CONSTITUTION_FILE = "CKTCLAW.md"
    SKILLS_DIR = "skills"
    AGENTS_DIR = "agents"

    def __init__(self, verbose: bool = False):
        self.verbose = verbose
        self._git_root: Optional[str] = None

    def _log(self, msg: str) -> None:
        if self.verbose:
            print(f"  [WorkspaceParser] {msg}")

    # ── Git Root Detection ──

    def _find_git_root(self, start_path: str) -> Optional[str]:
        """Walk upward to find .git directory."""
        if self._git_root is not None:
            return self._git_root

        current = Path(start_path).resolve()
        while current != current.parent:
            if (current / ".git").exists():
                self._git_root = str(current)
                return self._git_root
            current = current.parent

        self._git_root = ""  # sentinel: no git root found
        return None

    # ── Directory Discovery ──

    def _discover_cktclaw_dirs(self, cwd: str) -> List[str]:
        """
        Discover `.cktclaw/` directories from CWD upward to git root.
        Returns most-specific-first order.
        """
        cwd_path = Path(cwd).resolve()
        git_root = self._find_git_root(cwd)
        boundary = Path(git_root).resolve() if git_root else cwd_path

        discovered = []
        current = cwd_path

        while True:
            candidate = current / self.CKTCLAW_DIR
            if candidate.is_dir():
                discovered.append(str(candidate))
                self._log(f"Found {candidate}")

            if current == boundary:
                break
            parent = current.parent
            if parent == current:
                break
            current = parent

        return discovered

    # ── YAML Frontmatter ──

    @staticmethod
    def _parse_frontmatter(content: str) -> Tuple[Dict[str, Any], str]:
        """Extract YAML frontmatter delimited by --- from markdown."""
        if not content.startswith("---"):
            return {}, content

        lines = content.split("\n")
        end_idx = None
        for i in range(1, len(lines)):
            if lines[i].strip() == "---":
                end_idx = i
                break

        if end_idx is None:
            return {}, content

        fm_text = "\n".join(lines[1:end_idx])
        body = "\n".join(lines[end_idx + 1:]).strip()

        if yaml:
            try:
                fm = yaml.safe_load(fm_text) or {}
            except Exception:
                fm = {}
        else:
            # Minimal fallback: key: value parsing
            fm = {}
            for line in fm_text.split("\n"):
                if ":" in line:
                    k, v = line.split(":", 1)
                    fm[k.strip()] = v.strip().strip("\"'")

        return fm, body

    # ── Loaders ──

    async def _load_constitution(
        self, dirs: List[str],
    ) -> Tuple[Optional[str], Optional[str]]:
        """Load CKTCLAW.md from the first directory that has it."""
        for d in dirs:
            p = Path(d) / self.CONSTITUTION_FILE
            if p.is_file():
                try:
                    text = await asyncio.to_thread(p.read_text, encoding="utf-8")
                    self._log(f"Constitution: {p}")
                    return text, str(p)
                except Exception as e:
                    self._log(f"Failed to read {p}: {e}")
        return None, None

    async def _load_skills(self, dirs: List[str]) -> List[Dict[str, Any]]:
        """
        Load skills from `.cktclaw/skills/<name>/SKILL.md`.

        Frontmatter fields:
            name, description, when_to_use, skill_type (prompt|tool|workflow),
            user_invocable (bool), paths (list of globs for conditional activation)
        """
        skills: List[Dict[str, Any]] = []
        seen_names: set = set()

        for d in dirs:
            skills_dir = Path(d) / self.SKILLS_DIR
            if not skills_dir.is_dir():
                continue

            for skill_dir in sorted(skills_dir.iterdir()):
                if not skill_dir.is_dir():
                    continue

                skill_file = skill_dir / "SKILL.md"
                if not skill_file.is_file():
                    continue

                try:
                    text = await asyncio.to_thread(
                        skill_file.read_text, encoding="utf-8",
                    )
                    fm, body = self._parse_frontmatter(text)

                    name = fm.get("name", skill_dir.name)
                    if name in seen_names:
                        continue  # most-specific wins (CWD > parent)
                    seen_names.add(name)

                    # Normalize paths field
                    paths_raw = fm.get("paths")
                    if isinstance(paths_raw, str):
                        paths_raw = [
                            s.strip() for s in paths_raw.split(",") if s.strip()
                        ]

                    skills.append({
                        "name": name,
                        "description": fm.get("description", ""),
                        "when_to_use": fm.get("when_to_use"),
                        "skill_type": fm.get("skill_type", "prompt"),
                        "user_invocable": fm.get("user_invocable", True),
                        "paths": paths_raw,
                        "markdown_content": body,
                        "source_path": str(skill_file),
                    })
                    self._log(f"Skill: {name} ({skill_file})")

                except Exception as e:
                    self._log(f"Skill load error {skill_file}: {e}")

        return skills

    async def _load_agents(self, dirs: List[str]) -> List[Dict[str, Any]]:
        """
        Load agents from `.cktclaw/agents/<name>.md`.

        Frontmatter fields:
            name, role, description
        Body = system prompt for the agent.
        """
        agents: List[Dict[str, Any]] = []
        seen_names: set = set()

        for d in dirs:
            agents_dir = Path(d) / self.AGENTS_DIR
            if not agents_dir.is_dir():
                continue

            for agent_file in sorted(agents_dir.glob("*.md")):
                try:
                    text = await asyncio.to_thread(
                        agent_file.read_text, encoding="utf-8",
                    )
                    fm, body = self._parse_frontmatter(text)

                    name = fm.get("name", agent_file.stem)
                    if name in seen_names:
                        continue
                    seen_names.add(name)

                    agents.append({
                        "name": name,
                        "role": fm.get("role", "specialist"),
                        "description": fm.get("description", ""),
                        "system_prompt": body,
                        "source_path": str(agent_file),
                    })
                    self._log(f"Agent: {name} ({agent_file})")

                except Exception as e:
                    self._log(f"Agent load error {agent_file}: {e}")

        return agents

    # ── Main Entry Point ──

    async def load_project_behavior(
        self, cwd: Optional[str] = None,
    ) -> ProjectBehavior:
        """
        Scan `.cktclaw/` directories and return parsed ProjectBehavior.
        Safe to call even when no `.cktclaw/` exists — returns empty behavior.
        """
        if cwd is None:
            cwd = os.getcwd()

        dirs = self._discover_cktclaw_dirs(cwd)

        if not dirs:
            self._log("No .cktclaw/ found — using defaults")
            return ProjectBehavior(
                project_root=self._find_git_root(cwd) or cwd,
            )

        # Load all three components in parallel
        (constitution, constitution_path), skills, agents = await asyncio.gather(
            self._load_constitution(dirs),
            self._load_skills(dirs),
            self._load_agents(dirs),
        )

        behavior = ProjectBehavior(
            constitution=constitution,
            constitution_path=constitution_path,
            skills=skills,
            agents=agents,
            project_root=self._find_git_root(cwd) or cwd,
        )

        self._log(
            f"Result: constitution={'yes' if constitution else 'no'}, "
            f"{len(skills)} skill(s), {len(agents)} agent(s)"
        )
        return behavior


# ━━━━━━━━━━ Harness Integration ━━━━━━━━━━

async def inject_project_behavior(
    behavior: ProjectBehavior,
    cli_state,
) -> None:
    """
    Inject loaded ProjectBehavior into Harness singletons.

    Called once during startup. Wires:
    1. Skills → SkillRegistry
    2. Agents → CoordinatorManager (logged for future multi-agent)
    3. Constitution → CktMem Storage as PROJECT layer message

    Args:
        behavior: Parsed ProjectBehavior from WorkspaceParser
        cli_state: CLIState instance (has storage, context_manager, session_id, etc.)
    """
    if not behavior.has_content:
        return

    from ..harness.skills import (
        SkillDefinition, SkillType, LoadedFrom, register_skill,
    )

    # ── 1. Register project skills ──
    for sd in behavior.skills:
        try:
            # Normalize paths for conditional activation
            paths_list = sd.get("paths")
            if isinstance(paths_list, str):
                paths_list = [s.strip() for s in paths_list.split(",") if s.strip()]

            skill_def = SkillDefinition(
                name=sd["name"],
                skill_type=SkillType(sd.get("skill_type", "prompt")),
                description=sd.get("description", ""),
                when_to_use=sd.get("when_to_use"),
                user_invocable=sd.get("user_invocable", True),
                paths=paths_list,
                markdown_content=sd.get("markdown_content", ""),
                loaded_from=LoadedFrom.PROJECT_SETTINGS,
                source=sd.get("source_path", ""),
            )
            await register_skill(skill_def)
            print(f"  ✓ Project skill registered: {sd['name']}")
        except Exception as e:
            print(f"  ✗ Skill registration failed ({sd['name']}): {e}")

    # ── 2. Log discovered agents ──
    for ag in behavior.agents:
        print(
            f"  ℹ Agent discovered: {ag['name']} "
            f"(role={ag['role']}, {len(ag.get('system_prompt', ''))} chars)"
        )

    # ── 3. Inject constitution into CktMem PROJECT layer ──
    if behavior.constitution and cli_state.storage and cli_state.session_id:
        try:
            from ..cktmem.models import MessageRole, MessageType, ContextLayer

            await cli_state.storage.add_message(
                session_id=cli_state.session_id,
                role=MessageRole.SYSTEM,
                content=(
                    f"[Project Constitution — .cktclaw/CKTCLAW.md]\n\n"
                    f"{behavior.constitution}"
                ),
                msg_type=MessageType.CORE_CONTEXT,
                layer=ContextLayer.PROJECT,
                metadata={
                    "type": "project_constitution",
                    "source": behavior.constitution_path,
                },
            )
            print(f"  ✓ Constitution injected into PROJECT layer")
            print(f"    Source: {behavior.constitution_path}")
        except Exception as e:
            print(f"  ✗ Constitution injection failed: {e}")