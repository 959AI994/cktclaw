"""
CapabilityRegistry — unified read-only facade over ToolRegistry + SkillRegistry.

Does NOT merge or replace either registry. Provides a single lookup/execute
interface for the orchestrator and chat handlers. ToolRegistry is checked
first; SkillRegistry is the fallback.

Tolerant of two ToolRegistry shapes:
  - real ToolRegistry.list_tools() -> List[BaseTool]
  - test/legacy mocks            -> Dict[str, tool]
"""
import logging
import os
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


class CapabilityEntry:
    def __init__(self, name: str, description: str, source: str,
                 tool_obj=None, skill_obj=None):
        self.name = name
        self.description = description
        self.source = source
        self.tool_obj = tool_obj
        self.skill_obj = skill_obj

    def to_openai_schema(self) -> Dict[str, Any]:
        if self.source == "tool" and self.tool_obj is not None:
            return self.tool_obj.to_openai_schema()
        return {
            "type": "function",
            "function": {
                "name": self.name,
                "description": self.description,
                "parameters": {
                    "type": "object",
                    "properties": {
                        "args": {"type": "string",
                                 "description": "Natural language arguments"}
                    },
                    "required": ["args"],
                },
            },
        }


class CapabilityRegistry:
    def __init__(self):
        self._tool_registry = None
        self._skill_registry = None

    def _get_tool_registry(self):
        if self._tool_registry is None:
            try:
                from .tools import get_tool_registry
                self._tool_registry = get_tool_registry()
            except Exception as e:
                logger.debug(f"ToolRegistry unavailable: {e}")
        return self._tool_registry

    def _get_skill_registry(self):
        if self._skill_registry is None:
            try:
                from .harness import get_skill_registry
                self._skill_registry = get_skill_registry()
            except Exception as e:
                logger.debug(f"SkillRegistry unavailable: {e}")
        return self._skill_registry

    @staticmethod
    def _iter_tools(tool_reg):
        """Yield (name, tool) pairs from either a dict or a list interface."""
        raw = tool_reg.list_tools()
        if isinstance(raw, dict):
            yield from raw.items()
        else:
            for tool in raw:
                yield getattr(tool, "name", None), tool

    async def get(self, name: str) -> Optional[CapabilityEntry]:
        tool_reg = self._get_tool_registry()
        if tool_reg is not None:
            try:
                tool = tool_reg.get(name)
                if tool is not None:
                    return CapabilityEntry(
                        name=name,
                        description=getattr(tool, "description", name),
                        source="tool", tool_obj=tool)
            except Exception as e:
                logger.debug(f"ToolRegistry.get({name!r}) error: {e}")

        skill_reg = self._get_skill_registry()
        if skill_reg is not None:
            try:
                skill = await skill_reg.get_skill(name)
                if skill is not None:
                    return CapabilityEntry(
                        name=name,
                        description=getattr(skill, "description", name),
                        source="skill", skill_obj=skill)
            except Exception as e:
                logger.debug(f"SkillRegistry.get_skill({name!r}) error: {e}")

        return None

    async def list_all(self, user_invocable_only: bool = False) -> List[CapabilityEntry]:
        entries: Dict[str, CapabilityEntry] = {}

        tool_reg = self._get_tool_registry()
        if tool_reg is not None:
            try:
                for tool_name, tool in self._iter_tools(tool_reg):
                    if not tool_name:
                        continue
                    entries[tool_name] = CapabilityEntry(
                        name=tool_name,
                        description=getattr(tool, "description", tool_name),
                        source="tool", tool_obj=tool)
            except Exception as e:
                logger.debug(f"ToolRegistry.list_tools() error: {e}")

        skill_reg = self._get_skill_registry()
        if skill_reg is not None:
            try:
                skills = await skill_reg.list_skills()
                for skill in skills:
                    if user_invocable_only and not getattr(skill, "user_invocable", False):
                        continue
                    if skill.name not in entries:
                        entries[skill.name] = CapabilityEntry(
                            name=skill.name,
                            description=getattr(skill, "description", skill.name),
                            source="skill", skill_obj=skill)
            except Exception as e:
                logger.debug(f"SkillRegistry.list_skills() error: {e}")

        return list(entries.values())

    def get_required_permissions(self, name: str) -> List[str]:
        """
        Return the permission tokens a capability requires. Used by
        PermissionManager (Task 11). Conservative default: every capability
        requires a 'capability:<name>' token; destructive/system tools also
        require 'system:exec'.
        """
        tokens = [f"capability:{name}"]
        if name in {"bash", "shell", "exec"}:
            tokens.append("system:exec")
        return tokens

    async def resolve_intent(self, intent: str) -> Optional[Dict[str, Any]]:
        """
        Map a natural-language intent to a routing decision. Currently delegates
        to the keyword intent router; the async LLM fallback is future work.
        Returns an IntentRoute-shaped dict or None.
        """
        try:
            from .handlers.intent_router import detect_chip_design_intent_with_confidence
            route = detect_chip_design_intent_with_confidence(intent)
            if route:
                return route
            # Legacy fallback
            from .handlers.intent_router import detect_chip_design_intent
            skill_id = detect_chip_design_intent(intent)
            if skill_id:
                return {
                    "skill_id": skill_id,
                    "confidence": 0.75,
                    "score": 1,
                    "needs_orchestrator": skill_id.startswith("chip-"),
                    "task": intent,
                    "rationale": "keyword fast-path match",
                }
        except Exception as e:
            logger.debug(f"resolve_intent error: {e}")
        return None

    def _build_tool_context(self, context: Any):
        """Coerce arbitrary context into a ToolContext for real tools."""
        try:
            from .tools.base import ToolContext
        except Exception:
            return context
        if isinstance(context, ToolContext):
            return context
        if isinstance(context, dict):
            cli_state = context.get("cli_state")
            sid = getattr(cli_state, "session_id", "") if cli_state else ""
            return ToolContext(session_id=sid, working_dir=os.getcwd())
        return context  # pass-through (e.g. MagicMock in tests)

    @staticmethod
    def _audit(kind: str, capability: str, status: str, args=None, error=None) -> None:
        try:
            from .runtime.audit import audit_event
            audit_event(kind=kind, capability=capability, status=status,
                        args=args, error=error)
        except Exception:
            pass

    @staticmethod
    def _breaker():
        try:
            from .runtime.resilience import get_circuit_breaker
            return get_circuit_breaker()
        except Exception:
            return None

    @staticmethod
    def _tool_timeout() -> float:
        try:
            from .runtime.permissions import load_policy
            val = load_policy().get("reliability", {}).get("tool_timeout_s")
            if val:
                return float(val)
        except Exception:
            pass
        return 300.0

    async def _run_with_timeout(self, coro):
        try:
            from .runtime.resilience import with_timeout
            return await with_timeout(coro, self._tool_timeout())
        except ImportError:
            return await coro

    @staticmethod
    def _check_permission(name: str) -> Optional[str]:
        """Return a denial reason if the active policy denies *name*, else None."""
        try:
            from .runtime.permissions import get_permission_manager
            decision = get_permission_manager().check_capability(name)
            if not decision.allowed:
                return decision.reason
        except Exception:
            # Policy subsystem unavailable — do not block execution on errors.
            return None
        return None

    async def execute(self, name: str, args: Dict[str, Any], context: Any) -> str:
        denial = self._check_permission(name)
        if denial is not None:
            self._audit("permission", name, "deny", args=args, error=denial)
            return f"Permission denied: {denial}"

        entry = await self.get(name)
        if entry is None:
            self._audit("capability_call", name, "not_found", args=args)
            return f"Capability '{name}' not found in tool or skill registry."

        if entry.source == "tool" and entry.tool_obj is not None:
            breaker = self._breaker()
            if breaker is not None and breaker.is_open(name):
                self._audit("tool_call", name, "circuit_open", args=args)
                return (f"Tool '{name}' is temporarily disabled "
                        f"(circuit breaker open after repeated failures).")
            try:
                tool_ctx = self._build_tool_context(context)
                exec_coro = entry.tool_obj.execute(args, tool_ctx)
                result = await self._run_with_timeout(exec_coro)
                if breaker is not None:
                    breaker.record_success(name)
                self._audit("tool_call", name, "ok", args=args)
                return str(result.output) if hasattr(result, "output") else str(result)
            except Exception as e:
                if breaker is not None:
                    breaker.record_failure(name)
                self._audit("tool_call", name, "error", args=args, error=e)
                return f"Tool '{name}' execution error: {e}"

        if entry.source == "skill" and entry.skill_obj is not None:
            skill = entry.skill_obj
            if not callable(getattr(skill, "executor", None)):
                self._audit("skill_call", name, "error", args=args,
                            error="no executor")
                return f"Skill '{name}' has no executor."
            try:
                args_str = args.get("args", "") if isinstance(args, dict) and "args" in args else str(args)
                ctx_dict = context if isinstance(context, dict) else {"cli_state": context}
                result = await skill.executor(args_str, ctx_dict)
                self._audit("skill_call", name, "ok", args=args)
                if isinstance(result, list):
                    return "\n".join(
                        item.get("text", str(item)) for item in result
                        if isinstance(item, dict)
                    )
                return str(result)
            except Exception as e:
                self._audit("skill_call", name, "error", args=args, error=e)
                return f"Skill '{name}' execution error: {e}"

        return f"Capability '{name}' found but not executable."


_capability_registry: Optional[CapabilityRegistry] = None


def get_capability_registry() -> CapabilityRegistry:
    global _capability_registry
    if _capability_registry is None:
        _capability_registry = CapabilityRegistry()
    return _capability_registry
