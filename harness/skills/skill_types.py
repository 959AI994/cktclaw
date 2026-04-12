"""
Skill types — enums and the SkillDefinition payload used by the registry.

Covers:
1. SkillType discriminator
2. SkillDefinition metadata + optional executor hook
3. LoadedFrom provenance buckets
4. Lightweight helpers (display name, prompt assembly)

Principles:
- Treat skills as versioned assets (register, discover, reuse)
- Drive behavior from structured frontmatter (name, description, when_to_use)
- Support inline vs fork execution contexts
- Gate dangerous capabilities via allowed_tools / user_invocable flags
"""

from enum import Enum
from typing import Optional, List, Dict, Any, Callable, Awaitable
from pydantic import BaseModel, Field


class SkillType(str, Enum):
    """How the harness should interpret a skill body."""
    PROMPT = "prompt"           # Markdown / prompt-first skill
    TOOL = "tool"               # Callable tool skill
    WORKFLOW = "workflow"       # Multi-step workflow skill


class LoadedFrom(str, Enum):
    """Where a skill definition was discovered on disk."""
    BUNDLED = "bundled"                     # Shipped with CktClaw
    USER_SETTINGS = "userSettings"          # ~/.config / user scope
    PROJECT_SETTINGS = "projectSettings"    # Repo-local .cktclaw
    POLICY_SETTINGS = "policySettings"      # Policy bundle
    PLUGIN = "plugin"                       # Third-party plugin path
    MCP = "mcp"                             # MCP-provided skill
    COMMANDS_DEPRECATED = "commands_DEPRECATED"  # Legacy command bridge


class ExecutionContext(str, Enum):
    """Whether the skill runs in-process or in an isolated fork."""
    INLINE = "inline"   # Default: same interpreter
    FORK = "fork"       # Spawned worker / subprocess


class SkillDefinition(BaseModel):
    """
    Canonical skill record consumed by SkillRegistry and the CLI.

    Optional ``executor`` overrides default markdown prompt assembly.
    """
    # Identity
    name: str
    skill_type: SkillType = SkillType.PROMPT
    description: str
    display_name: Optional[str] = None
    aliases: List[str] = Field(default_factory=list)

    # Usage hints for routers / slash commands
    when_to_use: Optional[str] = None
    argument_hint: Optional[str] = None
    argument_names: List[str] = Field(default_factory=list)

    # Capability gates
    allowed_tools: List[str] = Field(default_factory=list)
    user_invocable: bool = True
    is_hidden: bool = False

    # Model overrides
    model: Optional[str] = None
    disable_model_invocation: bool = False

    # Execution
    execution_context: ExecutionContext = ExecutionContext.INLINE
    agent: Optional[str] = None
    effort: Optional[int] = None

    # Provenance
    loaded_from: LoadedFrom = LoadedFrom.BUNDLED
    source: str = "bundled"
    skill_root: Optional[str] = None
    version: Optional[str] = None

    # Path globs for conditional activation
    paths: Optional[List[str]] = None

    # Payload
    content_length: int = 0
    markdown_content: Optional[str] = None

    # Optional hook metadata
    hooks: Optional[Dict[str, Any]] = None

    # Optional async executor (args, context) -> Anthropic-style blocks
    executor: Optional[Callable[[str, Dict[str, Any]], Awaitable[List[Dict[str, Any]]]]] = None

    class Config:
        arbitrary_types_allowed = True
        use_enum_values = True

    def user_facing_name(self) -> str:
        """Label shown in menus (falls back to canonical name)."""
        return self.display_name or self.name

    def is_enabled(self) -> bool:
        """False when the skill should stay hidden from discovery."""
        return not self.is_hidden

    async def get_prompt_for_command(
        self,
        args: str,
        context: Optional[Dict[str, Any]] = None,
    ) -> List[Dict[str, Any]]:
        """
        Produce assistant-visible content blocks for this skill.

        Args:
            args: Raw argument string from the invocation.
            context: Optional structured context for executors.

        Returns:
            List of content parts (typically a single text block).
        """
        if self.executor:
            return await self.executor(args, context or {})

        content = self.markdown_content or self.description

        if args and self.argument_names:
            arg_values = args.split()
            for i, arg_name in enumerate(self.argument_names):
                if i < len(arg_values):
                    placeholder = f"${{{arg_name}}}"
                    content = content.replace(placeholder, arg_values[i])

        if self.skill_root:
            content = f"Base directory for this skill: {self.skill_root}\n\n{content}"

        return [{"type": "text", "text": content}]


def estimate_skill_frontmatter_tokens(skill: SkillDefinition) -> int:
    """
    Rough token estimate for registry statistics.

    Uses name + description + when_to_use only (ignores full markdown body).
    """
    frontmatter_text = " ".join(
        filter(None, [skill.name, skill.description, skill.when_to_use])
    )
    # Heuristic: ~4 characters per token for Latin text
    return len(frontmatter_text) // 4
