"""
Plugin Loader — discovers and loads plugins from filesystem.
"""

import importlib
import importlib.util
import logging
import sys
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Tuple

from .base import PluginInfo, PluginStatus, PluginType
from .manifest import PluginManifest
from .hooks import HookRegistry, get_hook_registry

logger = logging.getLogger(__name__)


class PluginLoader:
    """
    Discovers and loads plugins from plugin directories.

    A plugin is a directory containing a plugin.yaml manifest file.
    The loader validates the manifest and imports tool/hook modules.
    """

    def __init__(self, hook_registry: Optional[HookRegistry] = None):
        self._hook_registry = hook_registry or get_hook_registry()
        self._loaded_modules: Dict[str, Any] = {}

    def discover_plugins(self, plugin_dirs: List[Path]) -> List[Tuple[Path, PluginManifest]]:
        """
        Scan directories for plugin.yaml files.

        Args:
            plugin_dirs: List of directories to scan for plugins.

        Returns:
            List of (plugin_path, manifest) tuples.
        """
        discovered = []

        for plugin_dir in plugin_dirs:
            if not plugin_dir.is_dir():
                continue

            # Each subdirectory with a plugin.yaml is a plugin
            for candidate in plugin_dir.iterdir():
                if not candidate.is_dir():
                    continue

                manifest_path = candidate / "plugin.yaml"
                if not manifest_path.is_file():
                    # Also check plugin.yml
                    manifest_path = candidate / "plugin.yml"
                    if not manifest_path.is_file():
                        continue

                try:
                    manifest = PluginManifest.from_yaml(manifest_path)
                    discovered.append((candidate, manifest))
                    logger.debug(f"Discovered plugin: {manifest.name} v{manifest.version} at {candidate}")
                except Exception as e:
                    logger.warning(f"Failed to parse manifest at {manifest_path}: {e}")

        return discovered

    def load_plugin(self, plugin_path: Path, manifest: PluginManifest) -> PluginInfo:
        """
        Load a single plugin: import modules, register hooks.

        Args:
            plugin_path: Path to the plugin directory.
            manifest: Parsed plugin manifest.

        Returns:
            PluginInfo with status and contributions.
        """
        info = PluginInfo(
            name=manifest.name,
            version=manifest.version,
            description=manifest.description,
            author=manifest.author,
            path=plugin_path,
            status=PluginStatus.DISCOVERED,
        )

        contributions: Dict[PluginType, List[str]] = {}

        try:
            # Add plugin path to sys.path for imports
            plugin_str = str(plugin_path)
            if plugin_str not in sys.path:
                sys.path.insert(0, plugin_str)

            # Load tools
            tool_names = []
            for tool_entry in manifest.tools:
                tool_names.append(tool_entry.name)
            if tool_names:
                contributions[PluginType.TOOL] = tool_names

            # Load skills
            skill_names = []
            for skill_entry in manifest.skills:
                skill_path = plugin_path / skill_entry.path
                if skill_path.is_file():
                    skill_names.append(skill_entry.name)
                else:
                    logger.warning(
                        f"Plugin {manifest.name}: skill path not found: {skill_path}"
                    )
            if skill_names:
                contributions[PluginType.SKILL] = skill_names

            # Load workflows
            workflow_names = []
            for wf_entry in manifest.workflows:
                workflow_names.append(wf_entry.name)
            if workflow_names:
                contributions[PluginType.WORKFLOW] = workflow_names

            # Register hooks
            hook_names = []
            for hook_entry in manifest.hooks:
                handler = self._import_handler(plugin_path, hook_entry.handler)
                if handler:
                    self._hook_registry.register(
                        event=hook_entry.event,
                        handler=handler,
                        plugin_name=manifest.name,
                        priority=hook_entry.priority,
                    )
                    hook_names.append(hook_entry.event)
            if hook_names:
                contributions[PluginType.HOOK] = hook_names

            info.contributions = contributions
            info.status = PluginStatus.LOADED
            logger.info(f"Loaded plugin: {manifest.name} v{manifest.version}")

        except Exception as e:
            info.status = PluginStatus.ERROR
            info.error_message = str(e)
            logger.error(f"Failed to load plugin {manifest.name}: {e}")

        return info

    def unload_plugin(self, plugin_info: PluginInfo) -> None:
        """Unload a plugin: unregister hooks, remove from sys.path."""
        self._hook_registry.unregister_plugin(plugin_info.name)

        plugin_str = str(plugin_info.path)
        if plugin_str in sys.path:
            sys.path.remove(plugin_str)

        plugin_info.status = PluginStatus.DISABLED
        logger.info(f"Unloaded plugin: {plugin_info.name}")

    def _import_handler(
        self, plugin_path: Path, handler_spec: str
    ) -> Optional[Callable]:
        """
        Import a handler from a module:function spec.

        Args:
            plugin_path: Plugin root directory.
            handler_spec: "module.path:function_name" or "module.path"

        Returns:
            The callable, or None if import fails.
        """
        try:
            if ":" in handler_spec:
                module_path, func_name = handler_spec.rsplit(":", 1)
            else:
                module_path = handler_spec
                func_name = None

            # Try relative import from plugin directory
            module_file = plugin_path / module_path.replace(".", "/")
            if module_file.with_suffix(".py").is_file():
                spec = importlib.util.spec_from_file_location(
                    f"cktclaw_plugin_{module_path}",
                    module_file.with_suffix(".py"),
                )
                if spec and spec.loader:
                    module = importlib.util.module_from_spec(spec)
                    spec.loader.exec_module(module)
                    self._loaded_modules[module_path] = module

                    if func_name:
                        return getattr(module, func_name, None)
                    return module

            # Try standard import
            module = importlib.import_module(module_path)
            if func_name:
                return getattr(module, func_name, None)
            return module

        except Exception as e:
            logger.warning(f"Failed to import handler '{handler_spec}': {e}")
            return None
