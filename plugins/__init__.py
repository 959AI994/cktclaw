"""
CktClaw Plugin System — extensible tool/skill/workflow contributions.

Enables community contributions without modifying core code.
Plugins are directories with a plugin.yaml manifest.
"""

from .base import PluginBase, PluginType, PluginStatus
from .manifest import PluginManifest, ToolEntry, SkillEntry, WorkflowEntry
from .loader import PluginLoader
from .manager import PluginManager, get_plugin_manager
from .hooks import HookRegistry, HookType

__all__ = [
    "PluginBase",
    "PluginType",
    "PluginStatus",
    "PluginManifest",
    "ToolEntry",
    "SkillEntry",
    "WorkflowEntry",
    "PluginLoader",
    "PluginManager",
    "get_plugin_manager",
    "HookRegistry",
    "HookType",
]
