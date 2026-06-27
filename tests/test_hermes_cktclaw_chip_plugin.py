"""Tests for the Hermes-native CktClaw chip-design plugin."""

from __future__ import annotations

import importlib.util
import json
import subprocess
import sys
from pathlib import Path

import yaml

REPO_ROOT = Path(__file__).resolve().parents[1]
PLUGIN_ROOT = REPO_ROOT / "hermes_plugins" / "cktclaw-chip-design"


def _load_plugin_package():
    module_name = "cktclaw_chip_design_plugin_test"
    spec = importlib.util.spec_from_file_location(
        module_name,
        PLUGIN_ROOT / "__init__.py",
        submodule_search_locations=[str(PLUGIN_ROOT)],
    )
    module = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = module
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def test_tool_schemas_match_manifest_and_handlers():
    plugin = _load_plugin_package()
    manifest = yaml.safe_load((PLUGIN_ROOT / "plugin.yaml").read_text(encoding="utf-8"))
    manifest_tools = set(manifest["provides_tools"])
    schema_tools = {schema["name"] for schema in plugin.schemas.ALL_TOOL_SCHEMAS}

    assert schema_tools == manifest_tools
    assert schema_tools == set(plugin.tools.HANDLERS)
    for schema in plugin.schemas.ALL_TOOL_SCHEMAS:
        json.dumps(schema)
        assert schema["parameters"]["type"] == "object"


def test_missing_tool_failure_is_json(tmp_path):
    plugin = _load_plugin_package()
    result = plugin.tool_runtime.run_tool(
        "yosys",
        {
            "root": str(tmp_path / "empty-root"),
            "env": {"PATH": ""},
            "args": ["--version"],
            "timeout_s": 1,
        },
    )

    assert result["ok"] is False
    assert result["status"] == "MISSING"
    assert "yosys" in result["error"]


def test_skill_frontmatter_and_forbidden_runtime_words():
    forbidden = ("cktmem", "harness", "loop", "handlers", "web")
    skills = sorted((PLUGIN_ROOT / "skills").glob("*/*/SKILL.md"))

    assert len(skills) >= 49
    for skill_md in skills:
        text = skill_md.read_text(encoding="utf-8")
        assert text.startswith("---\n")
        frontmatter = text.split("---", 2)[1]
        metadata = yaml.safe_load(frontmatter)
        assert metadata["name"]
        assert metadata["description"]
        lower = text.lower()
        assert not [word for word in forbidden if word in lower], str(skill_md)


def test_skill_registration_scan_uses_category_prefixed_names():
    plugin = _load_plugin_package()
    names = {name for name, _ in plugin._discover_skill_files()}

    assert "digital-chip-design" in names
    assert "analog-chip-design" in names
    assert "digital-rtl-design" in names
    assert "analog-circuit-design" in names
    assert "rtl-enhancement-verilog-merge" in names
    assert "fpga-vivado-constraints" in names


def test_installer_dry_run_lists_actions_without_writing(tmp_path):
    install_root = tmp_path / "chip-root"
    script = PLUGIN_ROOT / "scripts" / "install_toolchain.py"
    proc = subprocess.run(
        [
            sys.executable,
            str(script),
            "--root",
            str(install_root),
            "--dry-run",
            "--include-hermes",
            "--json",
        ],
        capture_output=True,
        text=True,
        check=False,
    )

    assert proc.returncode == 0, proc.stderr
    result = json.loads(proc.stdout)
    assert result["dry_run"] is True
    assert result["ok"] is True
    assert any("digital-chip-design-agents" in " ".join(action["command"]) for action in result["actions"])
    assert any("hermes-agent" in " ".join(action["command"]) for action in result["actions"])
    assert not install_root.exists()


def test_mcp_config_generation_contains_selected_tool():
    plugin = _load_plugin_package()
    config = plugin.tool_runtime.mcp_config(["yosys"], root="/tmp/cktclaw-chip-test")

    assert "cktclaw-yosys" in config["mcp_servers"]
    entry = config["mcp_servers"]["cktclaw-yosys"]
    assert entry["command"] == "python3"
    assert "mcp_tool_server.py" in entry["args"][0]


def test_flow_plan_routes_rtl_sim_synth_tasks_to_closure_skill():
    plugin = _load_plugin_package()
    result = json.loads(
        plugin.tools.cktclaw_chip_flow_plan(
            {
                "task": "tiny_npu RTL compile, simulation PASS, Yosys synthesis netlist and QoR report",
                "domain": "auto",
            }
        )
    )

    assert result["domain"] == "digital"
    assert result["recommended_skills"][0] == "digital-eda-closure"
    assert "cktclaw_chip_closure_check" in result["recommended_tools"]
    assert any("QoR" in gate for gate in result["acceptance_gates"])


def test_closure_check_accepts_complete_digital_evidence(tmp_path):
    plugin = _load_plugin_package()
    outputs = tmp_path / "outputs"
    outputs.mkdir()
    (outputs / "compile.log").write_text("", encoding="utf-8")
    (outputs / "sim.log").write_text("ALL TESTS PASSED\n", encoding="utf-8")
    (outputs / "yosys.log").write_text("Found and reported 0 problems.\n", encoding="utf-8")
    (outputs / "tiny_npu_synth.v").write_text("module tiny_npu; endmodule\n", encoding="utf-8")
    (outputs / "tiny_npu_qor.rpt").write_text("10 wires\n20 cells\n", encoding="utf-8")

    result = json.loads(plugin.tools.cktclaw_chip_closure_check({"project_dir": str(tmp_path)}))

    assert result["ok"] is True
    assert {check["name"]: check["status"] for check in result["checks"]} == {
        "compile": "PASS",
        "simulation": "PASS",
        "yosys": "PASS",
        "netlist": "PASS",
        "qor": "PASS",
    }
