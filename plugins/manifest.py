"""
Plugin Manifest — YAML schema parsing and validation for plugin.yaml files.
"""

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional

import yaml


@dataclass
class ToolEntry:
    """A tool contribution from a plugin."""
    name: str
    handler: str  # module:ClassName format
    schema: Optional[str] = None  # path to JSON schema file
    description: str = ""
    read_only: bool = False
    category: str = "plugin"


@dataclass
class SkillEntry:
    """A skill contribution from a plugin."""
    name: str
    path: str  # relative path to SKILL.md
    orchestrator: Optional[str] = None  # relative path to orchestrator.md
    description: str = ""
    aliases: List[str] = field(default_factory=list)
    when_to_use: str = ""


@dataclass
class WorkflowEntry:
    """A workflow contribution from a plugin."""
    name: str
    path: str  # relative path to workflow module
    description: str = ""
    triggers: List[str] = field(default_factory=list)


@dataclass
class HookEntry:
    """A hook contribution from a plugin."""
    event: str  # e.g., "post_synthesis", "pre_placement"
    handler: str  # module:function format
    priority: int = 100  # lower = runs first


@dataclass
class PluginManifest:
    """Parsed plugin.yaml manifest."""
    name: str
    version: str
    description: str = ""
    author: str = ""
    cktclaw_version: str = ">=1.0.0"
    tools: List[ToolEntry] = field(default_factory=list)
    skills: List[SkillEntry] = field(default_factory=list)
    workflows: List[WorkflowEntry] = field(default_factory=list)
    hooks: List[HookEntry] = field(default_factory=list)
    dependencies: List[str] = field(default_factory=list)
    metadata: Dict[str, Any] = field(default_factory=dict)

    @classmethod
    def from_yaml(cls, path: Path) -> "PluginManifest":
        """Parse a plugin.yaml file into a PluginManifest."""
        if not path.is_file():
            raise FileNotFoundError(f"Plugin manifest not found: {path}")

        with open(path) as f:
            raw = yaml.safe_load(f)

        if not isinstance(raw, dict):
            raise ValueError(f"Invalid plugin manifest: {path}")

        name = raw.get("name")
        version = raw.get("version")
        if not name or not version:
            raise ValueError(f"Plugin manifest must have 'name' and 'version': {path}")

        # Parse tools
        tools = []
        for t in raw.get("tools", []):
            if isinstance(t, dict):
                tools.append(ToolEntry(
                    name=t.get("name", ""),
                    handler=t.get("handler", ""),
                    schema=t.get("schema"),
                    description=t.get("description", ""),
                    read_only=t.get("read_only", False),
                    category=t.get("category", "plugin"),
                ))

        # Parse skills
        skills = []
        for s in raw.get("skills", []):
            if isinstance(s, dict):
                skills.append(SkillEntry(
                    name=s.get("name", ""),
                    path=s.get("path", ""),
                    orchestrator=s.get("orchestrator"),
                    description=s.get("description", ""),
                    aliases=s.get("aliases", []),
                    when_to_use=s.get("when_to_use", ""),
                ))

        # Parse workflows
        workflows = []
        for w in raw.get("workflows", []):
            if isinstance(w, dict):
                workflows.append(WorkflowEntry(
                    name=w.get("name", ""),
                    path=w.get("path", ""),
                    description=w.get("description", ""),
                    triggers=w.get("triggers", []),
                ))

        # Parse hooks
        hooks = []
        raw_hooks = raw.get("hooks", {})
        if isinstance(raw_hooks, dict):
            for event, handler in raw_hooks.items():
                if isinstance(handler, str):
                    hooks.append(HookEntry(event=event, handler=handler))
                elif isinstance(handler, dict):
                    hooks.append(HookEntry(
                        event=event,
                        handler=handler.get("handler", ""),
                        priority=handler.get("priority", 100),
                    ))

        return cls(
            name=name,
            version=str(version),
            description=raw.get("description", ""),
            author=raw.get("author", ""),
            cktclaw_version=raw.get("cktclaw_version", ">=1.0.0"),
            tools=tools,
            skills=skills,
            workflows=workflows,
            hooks=hooks,
            dependencies=raw.get("dependencies", []),
            metadata=raw.get("metadata", {}),
        )

    @classmethod
    def from_json(cls, path: Path) -> "PluginManifest":
        """Parse a plugin.json manifest (Claude Code / superpowers format)."""
        import json
        raw = json.loads(path.read_text(encoding="utf-8"))
        name = raw.get("name") or path.parent.parent.name  # fallback to dir name
        version = str(raw.get("version", "0.0.0"))
        author_raw = raw.get("author", "")
        author = author_raw if isinstance(author_raw, str) else author_raw.get("name", "")
        return cls(
            name=name,
            version=version,
            description=raw.get("description", ""),
            author=author,
            # No tools/skills/hooks in this format — auto-scan will handle them
        )

    def to_dict(self) -> Dict[str, Any]:
        """Serialize manifest back to dict for writing."""
        result: Dict[str, Any] = {
            "name": self.name,
            "version": self.version,
        }
        if self.description:
            result["description"] = self.description
        if self.author:
            result["author"] = self.author
        if self.cktclaw_version != ">=1.0.0":
            result["cktclaw_version"] = self.cktclaw_version
        if self.tools:
            result["tools"] = [
                {"name": t.name, "handler": t.handler, "description": t.description}
                for t in self.tools
            ]
        if self.skills:
            result["skills"] = [
                {"name": s.name, "path": s.path, "description": s.description}
                for s in self.skills
            ]
        if self.workflows:
            result["workflows"] = [
                {"name": w.name, "path": w.path, "description": w.description}
                for w in self.workflows
            ]
        if self.hooks:
            result["hooks"] = {h.event: h.handler for h in self.hooks}
        return result
