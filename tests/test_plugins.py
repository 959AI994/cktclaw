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


class TestSkillMdParser:
    """Test SKILL.md frontmatter parsing."""

    def test_parse_skill_md_frontmatter(self, tmp_path):
        skill_dir = tmp_path / "my-skill"
        skill_dir.mkdir()
        skill_md = skill_dir / "SKILL.md"
        skill_md.write_text(
            "---\nname: my-skill\ndescription: Does things\nwhen_to_use: always\n---\n# Content\nHello.",
            encoding="utf-8",
        )

        from cktclaw.plugins.skill_loader import parse_skill_md
        skill_def = parse_skill_md(skill_md, "test-plugin")
        assert skill_def is not None
        assert skill_def.name == "my-skill"
        assert skill_def.description == "Does things"
        assert skill_def.when_to_use == "always"
        assert skill_def.source == "test-plugin"
        assert "Hello." in skill_def.markdown_content

    def test_parse_skill_md_no_frontmatter_uses_dir_name(self, tmp_path):
        skill_dir = tmp_path / "fallback-skill"
        skill_dir.mkdir()
        skill_md = skill_dir / "SKILL.md"
        skill_md.write_text("# No frontmatter here", encoding="utf-8")

        from cktclaw.plugins.skill_loader import parse_skill_md
        skill_def = parse_skill_md(skill_md, "plugin-x")
        assert skill_def is not None
        assert skill_def.name == "fallback-skill"


class TestAutoScanSkills:
    """Test auto-scan of skills/*/SKILL.md."""

    def test_auto_scan_skills_dir(self, tmp_path):
        # Plugin with skills dir but empty manifest.skills list
        plugin_dir = tmp_path / "my-plugin"
        plugin_dir.mkdir()
        with open(plugin_dir / "plugin.yaml", "w") as f:
            yaml.dump({"name": "my-plugin", "version": "1.0.0"}, f)

        skills_dir = plugin_dir / "skills" / "foo"
        skills_dir.mkdir(parents=True)
        (skills_dir / "SKILL.md").write_text(
            "---\nname: foo-skill\ndescription: Foo\n---\n# Foo",
            encoding="utf-8",
        )

        from cktclaw.harness.skills import get_skill_registry
        import asyncio

        manifest = PluginManifest.from_yaml(plugin_dir / "plugin.yaml")
        loader = PluginLoader()
        info = loader.load_plugin(plugin_dir, manifest)

        assert "foo-skill" in info.skill_names
        assert PluginType.SKILL in info.contributions

        reg = get_skill_registry()
        skills = asyncio.run(reg.list_skills())
        names = [s.name for s in skills]
        assert "foo-skill" in names


class TestJsonManifestDiscovery:
    """Test that .claude-plugin/plugin.json and plugin.json are discovered."""

    def test_json_manifest_discovery_claude_plugin(self, tmp_path):
        plugin_dir = tmp_path / "superpowers"
        plugin_dir.mkdir()
        claude_plugin_dir = plugin_dir / ".claude-plugin"
        claude_plugin_dir.mkdir()
        import json
        (claude_plugin_dir / "plugin.json").write_text(
            json.dumps({"name": "superpowers", "version": "1.2.3", "description": "Super"}),
            encoding="utf-8",
        )

        loader = PluginLoader()
        discovered = loader.discover_plugins([tmp_path])
        assert len(discovered) == 1
        assert discovered[0][1].name == "superpowers"
        assert discovered[0][1].version == "1.2.3"

    def test_json_manifest_discovery_root_level(self, tmp_path):
        plugin_dir = tmp_path / "my-ext"
        plugin_dir.mkdir()
        import json
        (plugin_dir / "plugin.json").write_text(
            json.dumps({"name": "my-ext", "version": "0.5.0"}),
            encoding="utf-8",
        )

        loader = PluginLoader()
        discovered = loader.discover_plugins([tmp_path])
        assert len(discovered) == 1
        assert discovered[0][1].name == "my-ext"


class TestPluginUnloadUnregistersSkills:
    """Test that unloading a plugin removes its skills from SkillRegistry."""

    def test_plugin_unload_unregisters_skills(self, tmp_path):
        import asyncio
        from cktclaw.harness.skills import get_skill_registry
        from cktclaw.harness.skills.skill_registry import SkillNotFoundError

        plugin_dir = tmp_path / "transient-plugin"
        plugin_dir.mkdir()
        with open(plugin_dir / "plugin.yaml", "w") as f:
            yaml.dump({"name": "transient-plugin", "version": "1.0.0"}, f)

        skills_dir = plugin_dir / "skills" / "bye-skill"
        skills_dir.mkdir(parents=True)
        (skills_dir / "SKILL.md").write_text(
            "---\nname: bye-skill\ndescription: Goes away\n---\n# Bye",
            encoding="utf-8",
        )

        manifest = PluginManifest.from_yaml(plugin_dir / "plugin.yaml")
        loader = PluginLoader()
        info = loader.load_plugin(plugin_dir, manifest)
        assert "bye-skill" in info.skill_names

        # Skill should be in registry
        reg = get_skill_registry()
        skill = asyncio.run(reg.get_skill("bye-skill"))
        assert skill.name == "bye-skill"

        # Now unload — skill should be gone
        loader.unload_plugin(info)
        with pytest.raises(SkillNotFoundError):
            asyncio.run(reg.get_skill("bye-skill"))
