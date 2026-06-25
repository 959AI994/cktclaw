"""
Tool Registry — singleton registry for discovering, registering, and accessing tools.
"""

import logging
from pathlib import Path
from typing import Dict, List, Optional, Type

from .base import BaseTool

logger = logging.getLogger(__name__)


class ToolRegistry:
    """
    Central registry for all CktClaw tools.

    Sources:
      1. Built-in tools (cktclaw/tools/eda/, system/, agent/)
      2. Plugin-contributed tools (from PluginManager)
      3. Legacy tools (wrapped from cktclaw/eda_tools/)

    Tools are registered by name and can be queried by category or capability.
    """

    def __init__(self):
        self._tools: Dict[str, BaseTool] = {}
        self._tool_classes: Dict[str, Type[BaseTool]] = {}
        self._sources: Dict[str, str] = {}  # tool_name -> source (builtin/plugin_name)

    def register(
        self,
        tool: BaseTool,
        source: str = "builtin",
        overwrite: bool = False,
    ) -> None:
        """
        Register a tool instance.

        Args:
            tool: Tool instance to register.
            source: Origin of the tool (e.g., "builtin", "plugin:openroad-advanced").
            overwrite: If True, replace existing tool with same name.
        """
        if not tool.name:
            raise ValueError("Tool must have a non-empty name")

        if tool.name in self._tools and not overwrite:
            logger.warning(
                f"Tool '{tool.name}' already registered (source: {self._sources.get(tool.name)}). "
                f"Use overwrite=True to replace."
            )
            return

        self._tools[tool.name] = tool
        self._sources[tool.name] = source
        logger.debug(f"Registered tool: {tool.name} (source: {source})")

    def register_class(
        self,
        tool_class: Type[BaseTool],
        source: str = "builtin",
    ) -> None:
        """Register a tool class (lazy instantiation)."""
        name = tool_class.name
        if not name:
            # Try to get from class attribute
            instance = tool_class()
            name = instance.name
            self.register(instance, source)
            return

        self._tool_classes[name] = tool_class
        self._sources[name] = source

    def get(self, name: str) -> Optional[BaseTool]:
        """Get a registered tool by name."""
        tool = self._tools.get(name)
        if tool:
            return tool

        # Try lazy instantiation
        tool_class = self._tool_classes.get(name)
        if tool_class:
            tool = tool_class()
            self._tools[name] = tool
            return tool

        return None

    def has(self, name: str) -> bool:
        """Check if a tool is registered."""
        return name in self._tools or name in self._tool_classes

    def unregister(self, name: str) -> bool:
        """Unregister a tool by name. Returns True if found and removed."""
        removed = False
        if name in self._tools:
            del self._tools[name]
            removed = True
        if name in self._tool_classes:
            del self._tool_classes[name]
            removed = True
        self._sources.pop(name, None)
        return removed

    def unregister_by_source(self, source: str) -> int:
        """Unregister all tools from a specific source. Returns count removed."""
        to_remove = [
            name for name, src in self._sources.items() if src == source
        ]
        for name in to_remove:
            self.unregister(name)
        return len(to_remove)

    def list_tools(self) -> List[BaseTool]:
        """Get all registered tool instances."""
        # Instantiate any lazy tools
        for name, cls in list(self._tool_classes.items()):
            if name not in self._tools:
                self._tools[name] = cls()

        return list(self._tools.values())

    def list_by_category(self, category: str) -> List[BaseTool]:
        """Get tools filtered by category."""
        return [t for t in self.list_tools() if t.category == category]

    def list_read_only(self) -> List[BaseTool]:
        """Get all read-only tools (safe for parallel execution)."""
        return [t for t in self.list_tools() if t.read_only]

    def list_names(self) -> List[str]:
        """Get all registered tool names."""
        return list(set(list(self._tools.keys()) + list(self._tool_classes.keys())))

    def get_openai_tools(self) -> List[Dict]:
        """Get all tools in OpenAI function calling format."""
        return [t.to_openai_schema() for t in self.list_tools()]

    def get_anthropic_tools(self) -> List[Dict]:
        """Get all tools in Anthropic tool_use format."""
        return [t.to_anthropic_schema() for t in self.list_tools()]

    def get_source(self, name: str) -> Optional[str]:
        """Get the source of a tool (builtin, plugin name, etc.)."""
        return self._sources.get(name)

    def auto_discover_builtin(self) -> int:
        """
        Auto-discover built-in tools from cktclaw/tools/eda/, system/, agent/.

        Returns number of tools discovered.
        """
        count = 0
        tools_dir = Path(__file__).parent

        for subdir in ["eda", "system", "agent"]:
            subdir_path = tools_dir / subdir
            if not subdir_path.is_dir():
                continue

            for py_file in subdir_path.glob("*_tool.py"):
                try:
                    module_name = f"cktclaw.tools.{subdir}.{py_file.stem}"
                    import importlib
                    module = importlib.import_module(module_name)

                    # Find BaseTool subclasses in the module
                    for attr_name in dir(module):
                        attr = getattr(module, attr_name)
                        if (
                            isinstance(attr, type)
                            and issubclass(attr, BaseTool)
                            and attr is not BaseTool
                            and attr.name  # Must have a name
                        ):
                            self.register_class(attr, source="builtin")
                            count += 1

                except Exception as e:
                    logger.debug(f"Failed to auto-discover from {py_file}: {e}")

        return count

    def summary(self) -> str:
        """Human-readable summary of registered tools."""
        tools = self.list_tools()
        if not tools:
            return "No tools registered."

        categories = {}
        for t in tools:
            categories.setdefault(t.category, []).append(t)

        lines = [f"Registered tools: {len(tools)} total"]
        for cat, cat_tools in sorted(categories.items()):
            lines.append(f"  [{cat}] {', '.join(t.name for t in cat_tools)}")
        return "\n".join(lines)


# Global singleton
_tool_registry: Optional[ToolRegistry] = None


def get_tool_registry() -> ToolRegistry:
    """Get or create the global ToolRegistry singleton."""
    global _tool_registry
    if _tool_registry is None:
        _tool_registry = ToolRegistry()
    return _tool_registry
