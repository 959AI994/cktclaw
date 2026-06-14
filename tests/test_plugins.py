"""
Tests for Plugin System.
"""

import tempfile
import shutil
from pathlib import Path

import pytest
import yaml

from cktclaw.plugins.manifest import PluginManifest, ToolEntry, SkillEntry
from cktclaw.plugins.base import PluginType, PluginStatus, PluginInfo
from cktclaw.plugins.hooks import HookRegistry, HookType
from cktclaw.plugins.loader import PluginLoader
from cktclaw.plugins.manager import PluginManager


class TestPluginManifest:
    """Test plugin.yaml parsing and validation."""

    def _make_manifest(self, tmp_path: Path, data: dict) -> Path:
        manifest_path = tmp_path / "plugin.yaml"
        with open(manifest_path, "w") as f:
            yaml.dump(data, f)
        return manifest_path

    def test_parse_minimal_manifest(self, tmp_path):
        path = self._make_manifest(tmp_path, {
            "name": "test-plugin",
            "version": "1.0.0",
        })
        manifest = PluginManifest.from_yaml(path)
        assert manifest.name == "test-plugin"
        assert manifest.version == "1.0.0"
        assert manifest.tools == []
        assert manifest.skills == []

    def test_parse_full_manifest(self, tmp_path):
        path = self._make_manifest(tmp_path, {
            "name": "eda-advanced",
            "version": "2.1.0",
            "description": "Advanced EDA tools",
            "author": "Test Author",
            "tools": [
                {"name": "custom_synth", "handler": "tools.synth:SynthTool"},
                {"name": "custom_sim", "handler": "tools.sim:SimTool", "read_only": True},
            ],
            "skills": [
                {"name": "advanced-pd", "path": "skills/pd.md"},
            ],
            "hooks": {
                "post_synthesis": "hooks.synth_check",
            },
        })
        manifest = PluginManifest.from_yaml(path)
        assert manifest.name == "eda-advanced"
        assert len(manifest.tools) == 2
        assert manifest.tools[0].name == "custom_synth"
        assert manifest.tools[1].read_only is True
        assert len(manifest.skills) == 1
        assert len(manifest.hooks) == 1
        assert manifest.hooks[0].event == "post_synthesis"

    def test_missing_name_raises(self, tmp_path):
        path = self._make_manifest(tmp_path, {"version": "1.0.0"})
        with pytest.raises(ValueError, match="must have 'name'"):
            PluginManifest.from_yaml(path)

    def test_missing_file_raises(self, tmp_path):
        with pytest.raises(FileNotFoundError):
            PluginManifest.from_yaml(tmp_path / "nonexistent.yaml")

    def test_to_dict_roundtrip(self, tmp_path):
        path = self._make_manifest(tmp_path, {
            "name": "roundtrip",
            "version": "1.0.0",
            "tools": [{"name": "t1", "handler": "m:C", "description": "desc"}],
        })
        manifest = PluginManifest.from_yaml(path)
        d = manifest.to_dict()
        assert d["name"] == "roundtrip"
        assert len(d["tools"]) == 1


class TestHookRegistry:
    """Test hook registration and firing."""

    def test_register_and_fire(self):
        registry = HookRegistry()
        results = []
        registry.register("test_event", lambda: results.append("called"))

        import asyncio
        asyncio.run(registry.fire("test_event"))
        assert results == ["called"]

    def test_priority_order(self):
        registry = HookRegistry()
        results = []
        registry.register("evt", lambda: results.append("second"), priority=200)
        registry.register("evt", lambda: results.append("first"), priority=100)

        import asyncio
        asyncio.run(registry.fire("evt"))
        assert results == ["first", "second"]

    def test_unregister_plugin(self):
        registry = HookRegistry()
        registry.register("evt", lambda: None, plugin_name="p1")
        registry.register("evt", lambda: None, plugin_name="p2")
        removed = registry.unregister_plugin("p1")
        assert removed == 1
        assert len(registry.get_handlers_for_event("evt")) == 1

    def test_fire_nonexistent_event(self):
        registry = HookRegistry()
        import asyncio
        results = asyncio.run(registry.fire("nonexistent"))
        assert results == []


class TestPluginLoader:
    """Test plugin discovery and loading."""

    def test_discover_plugins(self, tmp_path):
        # Create a plugin directory
        plugin_dir = tmp_path / "test-plugin"
        plugin_dir.mkdir()
        with open(plugin_dir / "plugin.yaml", "w") as f:
            yaml.dump({"name": "test", "version": "1.0"}, f)

        loader = PluginLoader()
        discovered = loader.discover_plugins([tmp_path])
        assert len(discovered) == 1
        assert discovered[0][1].name == "test"

    def test_discover_empty_dir(self, tmp_path):
        loader = PluginLoader()
        discovered = loader.discover_plugins([tmp_path])
        assert discovered == []

    def test_load_plugin(self, tmp_path):
        plugin_dir = tmp_path / "my-plugin"
        plugin_dir.mkdir()
        with open(plugin_dir / "plugin.yaml", "w") as f:
            yaml.dump({
                "name": "my-plugin",
                "version": "0.1.0",
                "tools": [{"name": "my_tool", "handler": "tools:MyTool"}],
            }, f)

        manifest = PluginManifest.from_yaml(plugin_dir / "plugin.yaml")
        loader = PluginLoader()
        info = loader.load_plugin(plugin_dir, manifest)
        assert info.name == "my-plugin"
        assert info.status == PluginStatus.LOADED
        assert PluginType.TOOL in info.contributions


class TestPluginManager:
    """Test plugin install/uninstall/list."""

    def test_install_from_path(self, tmp_path):
        # Create source plugin
        src = tmp_path / "source" / "test-plugin"
        src.mkdir(parents=True)
        with open(src / "plugin.yaml", "w") as f:
            yaml.dump({"name": "test-install", "version": "1.0.0"}, f)

        mgr = PluginManager(plugin_dirs=[tmp_path / "installed"])
        (tmp_path / "installed").mkdir()

        info = mgr.install_from_path(str(src))
        assert info is not None
        assert info.name == "test-install"
        assert "test-install" in mgr.loaded_plugins

    def test_list_no_plugins(self, tmp_path):
        mgr = PluginManager(plugin_dirs=[tmp_path])
        loaded = mgr.discover_and_load_all()
        assert loaded == []
