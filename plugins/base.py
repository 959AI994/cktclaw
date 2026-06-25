"""
Plugin Base — abstract base class and type definitions for CktClaw plugins.
"""

from abc import ABC
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any, Dict, List, Optional


class PluginType(str, Enum):
    """Plugin contribution types."""
    TOOL = "tool"
    SKILL = "skill"
    WORKFLOW = "workflow"
    HOOK = "hook"


class PluginStatus(str, Enum):
    """Plugin lifecycle status."""
    DISCOVERED = "discovered"
    LOADED = "loaded"
    ACTIVE = "active"
    ERROR = "error"
    DISABLED = "disabled"


@dataclass
class PluginInfo:
    """Runtime information about a loaded plugin."""
    name: str
    version: str
    description: str
    author: str
    path: Path
    status: PluginStatus = PluginStatus.DISCOVERED
    error_message: Optional[str] = None
    contributions: Dict[PluginType, List[str]] = field(default_factory=dict)
    skill_names: List[str] = field(default_factory=list)


class PluginBase(ABC):
    """
    Base class for CktClaw plugins.

    Plugins don't need to subclass this directly — the plugin system
    loads from plugin.yaml manifests. This class is provided for plugins
    that want to implement custom initialization logic.
    """

    def __init__(self, plugin_path: Path):
        self.plugin_path = plugin_path
        self._metadata: Dict[str, Any] = {}

    @property
    def name(self) -> str:
        return self._metadata.get("name", "unknown")

    @property
    def version(self) -> str:
        return self._metadata.get("version", "0.0.0")

    def on_load(self) -> None:
        """Called when plugin is loaded. Override for custom init."""
        pass

    def on_unload(self) -> None:
        """Called when plugin is unloaded. Override for cleanup."""
        pass

    def on_activate(self) -> None:
        """Called when plugin becomes active in a session."""
        pass
