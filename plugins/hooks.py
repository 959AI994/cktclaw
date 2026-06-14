"""
Plugin Hooks — lifecycle hook registry for cross-cutting plugin events.
"""

import asyncio
import logging
from enum import Enum
from typing import Any, Callable, Dict, List, Optional, Awaitable

logger = logging.getLogger(__name__)


class HookType(str, Enum):
    """Standard hook events in CktClaw."""
    # Plugin lifecycle
    ON_PLUGIN_LOAD = "on_plugin_load"
    ON_PLUGIN_UNLOAD = "on_plugin_unload"

    # Tool execution
    PRE_TOOL_CALL = "pre_tool_call"
    POST_TOOL_CALL = "post_tool_call"

    # EDA flow stages
    PRE_SYNTHESIS = "pre_synthesis"
    POST_SYNTHESIS = "post_synthesis"
    PRE_PLACEMENT = "pre_placement"
    POST_PLACEMENT = "post_placement"
    PRE_ROUTING = "pre_routing"
    POST_ROUTING = "post_routing"
    PRE_STA = "pre_sta"
    POST_STA = "post_sta"

    # Agent events
    PRE_AGENT_SPAWN = "pre_agent_spawn"
    POST_AGENT_COMPLETE = "post_agent_complete"

    # Session events
    ON_SESSION_START = "on_session_start"
    ON_SESSION_END = "on_session_end"


class HookRegistration:
    """A single registered hook handler."""

    def __init__(
        self,
        event: str,
        handler: Callable[..., Any],
        plugin_name: str = "core",
        priority: int = 100,
    ):
        self.event = event
        self.handler = handler
        self.plugin_name = plugin_name
        self.priority = priority


class HookRegistry:
    """
    Global hook registry.

    Plugins register handlers for specific events. When an event fires,
    all registered handlers run in priority order (lower = earlier).
    """

    def __init__(self):
        self._hooks: Dict[str, List[HookRegistration]] = {}

    def register(
        self,
        event: str,
        handler: Callable[..., Any],
        plugin_name: str = "core",
        priority: int = 100,
    ) -> None:
        """Register a hook handler for an event."""
        if event not in self._hooks:
            self._hooks[event] = []

        reg = HookRegistration(
            event=event,
            handler=handler,
            plugin_name=plugin_name,
            priority=priority,
        )
        self._hooks[event].append(reg)
        # Keep sorted by priority
        self._hooks[event].sort(key=lambda r: r.priority)

    def unregister_plugin(self, plugin_name: str) -> int:
        """Remove all hooks from a specific plugin. Returns count removed."""
        removed = 0
        for event in list(self._hooks.keys()):
            before = len(self._hooks[event])
            self._hooks[event] = [
                h for h in self._hooks[event] if h.plugin_name != plugin_name
            ]
            removed += before - len(self._hooks[event])
            if not self._hooks[event]:
                del self._hooks[event]
        return removed

    async def fire(self, event: str, **kwargs: Any) -> List[Any]:
        """
        Fire an event, running all registered handlers in priority order.

        Handlers can be sync or async. Results are collected and returned.
        """
        handlers = self._hooks.get(event, [])
        results = []

        for reg in handlers:
            try:
                result = reg.handler(**kwargs)
                if asyncio.iscoroutine(result):
                    result = await result
                results.append(result)
            except Exception as e:
                logger.warning(
                    f"Hook {reg.plugin_name}:{reg.event} failed: {e}"
                )
                results.append(None)

        return results

    def get_registered_events(self) -> List[str]:
        """List all events that have at least one handler."""
        return list(self._hooks.keys())

    def get_handlers_for_event(self, event: str) -> List[HookRegistration]:
        """Get all handlers for an event."""
        return self._hooks.get(event, [])

    def clear(self) -> None:
        """Remove all hooks (for testing)."""
        self._hooks.clear()


# Global hook registry singleton
_hook_registry: Optional[HookRegistry] = None


def get_hook_registry() -> HookRegistry:
    """Get the global hook registry."""
    global _hook_registry
    if _hook_registry is None:
        _hook_registry = HookRegistry()
    return _hook_registry
