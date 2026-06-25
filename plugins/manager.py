"""
Plugin Manager — high-level API for plugin install/uninstall/list operations.
"""

import json
import logging
import shutil
import subprocess
from pathlib import Path
from typing import Dict, List, Optional

from .base import PluginInfo, PluginStatus, PluginType
from .manifest import PluginManifest
from .loader import PluginLoader
from .hooks import HookRegistry, get_hook_registry

logger = logging.getLogger(__name__)

# Default plugin directories
_USER_PLUGINS_DIR = Path.home() / ".cktclaw" / "plugins"
_PROJECT_PLUGINS_DIRNAME = ".cktclaw/plugins"


class PluginManager:
    """
    High-level plugin management: install, uninstall, list, activate.

    Plugins are stored in:
      - ~/.cktclaw/plugins/ (user-global)
      - .cktclaw/plugins/ (project-local, relative to working dir)
    """

    def __init__(
        self,
        plugin_dirs: Optional[List[Path]] = None,
        hook_registry: Optional[HookRegistry] = None,
    ):
        self._hook_registry = hook_registry or get_hook_registry()
        self._loader = PluginLoader(self._hook_registry)
        self._plugins: Dict[str, PluginInfo] = {}
        self._manifests: Dict[str, PluginManifest] = {}

        # Set up plugin directories
        if plugin_dirs:
            self._plugin_dirs = plugin_dirs
        else:
            self._plugin_dirs = [_USER_PLUGINS_DIR]
            # Add project-local plugins if we're in a project
            project_plugins = Path.cwd() / _PROJECT_PLUGINS_DIRNAME
            if project_plugins.is_dir():
                self._plugin_dirs.append(project_plugins)

        # Ensure user plugins dir exists
        _USER_PLUGINS_DIR.mkdir(parents=True, exist_ok=True)

    @property
    def plugin_dirs(self) -> List[Path]:
        """Plugin search directories."""
        return list(self._plugin_dirs)

    @property
    def loaded_plugins(self) -> Dict[str, PluginInfo]:
        """All loaded plugins by name."""
        return dict(self._plugins)

    def discover_and_load_all(self) -> List[PluginInfo]:
        """Discover and load all plugins from configured directories."""
        discovered = self._loader.discover_plugins(self._plugin_dirs)

        loaded = []
        for plugin_path, manifest in discovered:
            # Skip if already loaded
            if manifest.name in self._plugins:
                loaded.append(self._plugins[manifest.name])
                continue

            info = self._loader.load_plugin(plugin_path, manifest)
            self._plugins[manifest.name] = info
            self._manifests[manifest.name] = manifest
            loaded.append(info)

        return loaded

    def install_from_path(self, source_path: str) -> Optional[PluginInfo]:
        """
        Install a plugin from a local directory path.

        Creates a symlink in the user plugins directory.
        """
        source = Path(source_path).resolve()

        if not source.is_dir():
            logger.error(f"Plugin source is not a directory: {source}")
            return None

        # Find and validate manifest
        manifest_path = source / "plugin.yaml"
        if not manifest_path.is_file():
            manifest_path = source / "plugin.yml"
            if not manifest_path.is_file():
                logger.error(f"No plugin.yaml found in: {source}")
                return None

        try:
            manifest = PluginManifest.from_yaml(manifest_path)
        except Exception as e:
            logger.error(f"Invalid plugin manifest: {e}")
            return None

        # Create symlink in user plugins dir
        target = _USER_PLUGINS_DIR / manifest.name
        if target.exists():
            logger.warning(f"Plugin '{manifest.name}' already installed, updating...")
            if target.is_symlink():
                target.unlink()
            else:
                shutil.rmtree(target)

        target.symlink_to(source)
        logger.info(f"Installed plugin '{manifest.name}' from {source}")

        # Load the plugin
        info = self._loader.load_plugin(source, manifest)
        self._plugins[manifest.name] = info
        self._manifests[manifest.name] = manifest

        # Save to registry
        self._save_registry()

        return info

    def install_from_git(self, git_url: str) -> Optional[PluginInfo]:
        """
        Install a plugin from a git repository URL.

        Clones into the user plugins directory.
        """
        # Determine plugin name from URL
        repo_name = git_url.rstrip("/").split("/")[-1]
        if repo_name.endswith(".git"):
            repo_name = repo_name[:-4]

        target = _USER_PLUGINS_DIR / repo_name

        if target.exists():
            logger.warning(f"Directory exists: {target}, removing...")
            shutil.rmtree(target)

        try:
            subprocess.run(
                ["git", "clone", "--depth=1", git_url, str(target)],
                check=True,
                capture_output=True,
                text=True,
                timeout=60,
            )
        except subprocess.CalledProcessError as e:
            logger.error(f"Git clone failed: {e.stderr}")
            return None
        except FileNotFoundError:
            logger.error("git not found. Install git to use plugin install from URL.")
            return None

        # Find manifest in cloned repo
        manifest_path = target / "plugin.yaml"
        if not manifest_path.is_file():
            manifest_path = target / "plugin.yml"
            if not manifest_path.is_file():
                logger.error(f"No plugin.yaml in cloned repo: {target}")
                shutil.rmtree(target)
                return None

        try:
            manifest = PluginManifest.from_yaml(manifest_path)
        except Exception as e:
            logger.error(f"Invalid plugin manifest: {e}")
            shutil.rmtree(target)
            return None

        # Rename directory to match plugin name if different
        if manifest.name != repo_name:
            new_target = _USER_PLUGINS_DIR / manifest.name
            if new_target.exists():
                shutil.rmtree(new_target)
            target.rename(new_target)
            target = new_target

        info = self._loader.load_plugin(target, manifest)
        self._plugins[manifest.name] = info
        self._manifests[manifest.name] = manifest

        self._save_registry()

        return info

    def uninstall(self, plugin_name: str) -> bool:
        """
        Uninstall a plugin by name.

        Removes the plugin directory/symlink and unloads it.
        """
        info = self._plugins.get(plugin_name)
        if not info:
            logger.error(f"Plugin not found: {plugin_name}")
            return False

        # Unload
        self._loader.unload_plugin(info)

        # Remove from filesystem
        if info.path.is_symlink():
            info.path.unlink()
        elif info.path.is_dir():
            shutil.rmtree(info.path)

        # Remove from state
        del self._plugins[plugin_name]
        self._manifests.pop(plugin_name, None)

        self._save_registry()

        logger.info(f"Uninstalled plugin: {plugin_name}")
        return True

    def get_plugin(self, name: str) -> Optional[PluginInfo]:
        """Get a loaded plugin by name."""
        return self._plugins.get(name)

    def get_manifest(self, name: str) -> Optional[PluginManifest]:
        """Get a plugin's manifest by name."""
        return self._manifests.get(name)

    def list_tools(self) -> Dict[str, str]:
        """Get all tools contributed by plugins. Returns {tool_name: plugin_name}."""
        tools = {}
        for name, manifest in self._manifests.items():
            for tool in manifest.tools:
                tools[tool.name] = name
        return tools

    def list_skills(self) -> Dict[str, str]:
        """Get all skills contributed by plugins. Returns {skill_name: plugin_name}."""
        skills = {}
        for name, manifest in self._manifests.items():
            for skill in manifest.skills:
                skills[skill.name] = name
        return skills

    def _save_registry(self) -> None:
        """Persist the plugin registry to disk."""
        registry_path = _USER_PLUGINS_DIR / "registry.json"
        data = {}
        for name, info in self._plugins.items():
            data[name] = {
                "version": info.version,
                "path": str(info.path),
                "status": info.status.value,
            }
        registry_path.write_text(json.dumps(data, indent=2))


# Global singleton
_plugin_manager: Optional[PluginManager] = None


def get_plugin_manager(
    plugin_dirs: Optional[List[Path]] = None,
) -> PluginManager:
    """Get or create the global PluginManager singleton."""
    global _plugin_manager
    if _plugin_manager is None:
        _plugin_manager = PluginManager(plugin_dirs=plugin_dirs)
    return _plugin_manager
