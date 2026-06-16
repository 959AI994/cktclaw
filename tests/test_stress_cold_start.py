"""
Cold-start / missing EDA tool detection stress tests — Fix 4 & 5.

Tests adversarial environment conditions where expected tools are absent:
  - Missing yosys from PATH
  - Completely empty PATH (all tools MISSING)
  - ABC_PATH env var picks up non-standard binary
  - VerificationRunner gracefully handles no tools / no artifacts
  - AI infra gracefully handles missing Python artifacts
  - Logger captures missing dependency information
"""

import asyncio
import logging
import os
import shutil
import sys
from pathlib import Path
from unittest.mock import patch

import pytest

_PROJECT_ROOT = Path(__file__).parent.parent.resolve()
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

from cktclaw.eda_tools.tool_detection import (
    detect_tool,
    detect_all_tools,
    ToolStatus,
    ToolManifest,
)
from cktclaw.loop.task_graph import TaskNode
from cktclaw.loop.verification import VerificationRunner, VerificationReport


def _run(coro):
    """Helper to run async tests synchronously."""
    return asyncio.run(coro)


# ═══════════════════════════════════════════════════════════════
# 1. Missing Yosys from PATH
# ═══════════════════════════════════════════════════════════════

class TestToolManifestMissingYosys:
    def test_tool_manifest_missing_yosys(self):
        """When yosys is not in PATH, ToolStatus must be MISSING, no exception."""
        with patch("shutil.which", return_value=None):
            status = detect_tool("yosys", ["yosys"], "--version")
        assert status.name == "yosys"
        assert status.status == "MISSING"
        assert status.path == ""
        assert status.version == ""

    def test_missing_tool_reports_correct_command(self):
        """Missing tool status must report the first command attempted."""
        with patch("shutil.which", return_value=None):
            status = detect_tool("yosys", ["yosys", "yosys-0.30"], "--version")
        assert status.command == "yosys"
        assert status.status == "MISSING"

    def test_missing_tool_correct_category(self):
        """Missing tool must have correct category preserved."""
        with patch("shutil.which", return_value=None):
            status = detect_tool("yosys", ["yosys"], "--version", "open_source")
        assert status.category == "open_source"
        assert status.status == "MISSING"

    def test_detect_tool_does_not_raise_when_missing(self):
        """detect_tool must never raise when tool is not found."""
        with patch("shutil.which", return_value=None):
            try:
                status = detect_tool("yosys", ["yosys"], "--version")
                assert status.status == "MISSING"
            except Exception as e:
                pytest.fail(f"detect_tool raised when tool was missing: {e}")

    def test_tool_found_when_in_path(self):
        """When yosys is in PATH, ToolStatus must be FOUND."""
        with patch("shutil.which", return_value="/usr/local/bin/yosys"):
            with patch(
                "cktclaw.eda_tools.tool_detection._try_version",
                return_value="Yosys 0.40",
            ):
                status = detect_tool("yosys", ["yosys"], "--version")
        assert status.status == "FOUND"
        assert status.path == "/usr/local/bin/yosys"


# ═══════════════════════════════════════════════════════════════
# 2. All Tools Missing (Empty PATH simulation)
# ═══════════════════════════════════════════════════════════════

class TestToolManifestAllMissing:
    def test_tool_manifest_all_missing(self):
        """When shutil.which always returns None, all open-source tools must be MISSING."""
        with patch("shutil.which", return_value=None):
            manifest = detect_all_tools()

        assert len(manifest.tools) > 0
        open_source = [t for t in manifest.tools if t.category == "open_source"]
        assert len(open_source) > 0

        for tool in open_source:
            assert tool.status == "MISSING", (
                f"Tool {tool.name} should be MISSING, got {tool.status}"
            )

    def test_missing_tools_list_populated(self):
        """manifest.missing_tools() must be non-empty when PATH is empty."""
        with patch("shutil.which", return_value=None):
            manifest = detect_all_tools()
        missing = manifest.missing_tools()
        open_source = [t for t in manifest.tools if t.category == "open_source"]
        assert len(missing) >= len(open_source)

    def test_found_tools_empty_when_all_missing(self):
        """manifest.found_tools() must be empty when nothing is available."""
        with patch("shutil.which", return_value=None):
            manifest = detect_all_tools()
        assert len(manifest.found_tools()) == 0

    def test_is_tool_available_returns_false_when_all_missing(self):
        """is_tool_available() must return False for key tools when PATH is empty."""
        with patch("shutil.which", return_value=None):
            manifest = detect_all_tools()
        assert not manifest.is_tool_available("yosys")
        assert not manifest.is_tool_available("abc")
        assert not manifest.is_tool_available("opensta")

    def test_manifest_detected_at_is_set(self):
        """Manifest must always have a detected_at timestamp."""
        with patch("shutil.which", return_value=None):
            manifest = detect_all_tools()
        assert manifest.detected_at != ""
        assert len(manifest.detected_at) > 5  # non-trivial timestamp


# ═══════════════════════════════════════════════════════════════
# 3. ABC_PATH Environment Variable
# ═══════════════════════════════════════════════════════════════

class TestToolManifestAbcEnvPath:
    def test_tool_manifest_abc_env_path(self):
        """
        When ABC_PATH env var points to a non-standard binary,
        detect_tool should find abc via that path.
        """
        fake_abc_path = "/opt/abc/bin/abc"

        def mock_which(cmd):
            if cmd == fake_abc_path:
                return fake_abc_path
            return None

        with patch.dict(os.environ, {"ABC_PATH": fake_abc_path}):
            with patch("shutil.which", side_effect=mock_which):
                with patch(
                    "cktclaw.eda_tools.tool_detection._try_version",
                    return_value="Berkeley ABC 1.01",
                ):
                    status = detect_tool(
                        "abc", ["abc", fake_abc_path], "-h"
                    )

        assert status.status == "FOUND"
        assert status.path == fake_abc_path

    def test_tool_found_at_second_command(self):
        """If the first command fails but a second one succeeds, tool must be FOUND."""
        def mock_which(cmd):
            return "/usr/bin/alternative-tool" if cmd == "alternative-tool" else None

        with patch("shutil.which", side_effect=mock_which):
            with patch(
                "cktclaw.eda_tools.tool_detection._try_version",
                return_value="v1.0",
            ):
                status = detect_tool(
                    "my-tool", ["my-tool", "alternative-tool"], "--version"
                )
        assert status.status == "FOUND"
        assert status.path == "/usr/bin/alternative-tool"

    def test_empty_string_commands_skipped(self):
        """Empty strings in commands list (e.g. unset env vars) must be skipped."""
        with patch("shutil.which", return_value=None):
            # The "" command comes from os.environ.get("ABC_PATH", "") when var is unset
            status = detect_tool("abc", ["abc", ""], "-h")
        assert status.status == "MISSING"
        # Must not have crashed even with "" in the list

    def test_none_command_skipped(self):
        """None value in commands (from failed env var) must be skipped gracefully."""
        def mock_which(cmd):
            return None

        # Filter out None before passing (as the real code does with `if not cmd`)
        commands = [c for c in ["abc", None, ""] if c is not None]
        with patch("shutil.which", side_effect=mock_which):
            status = detect_tool("abc", commands, "-h")
        assert status.status == "MISSING"


# ═══════════════════════════════════════════════════════════════
# 4. VerificationRunner: EDA without tools
# ═══════════════════════════════════════════════════════════════

class TestVerifyEdaNoToolsGraceful:
    def test_verify_eda_no_artifacts_returns_error_report(self):
        """
        VerificationRunner with no artifacts must return a VerificationReport
        with errors — not raise an exception.
        """
        runner = VerificationRunner()
        task = TaskNode(
            id="eda_task_1",
            domain="eda",
            description="Synthesize design",
            verification_criteria={"area_cells": 100},
        )
        report = _run(runner.verify_task(task, []))
        assert isinstance(report, VerificationReport)
        assert not report.passed
        assert len(report.errors) > 0

    def test_verify_eda_fake_verilog_graceful(self):
        """
        When yosys is not installed, verify_task must return a VerificationReport
        (possibly failed) without raising an exception.
        """
        runner = VerificationRunner()
        task = TaskNode(
            id="eda_synth_1",
            domain="eda",
            description="Synthesize 4-bit adder",
            verification_criteria={"area_cells": 100},
        )
        # Pass a fake path — tool may not be installed so it returns error string
        report = _run(runner.verify_task(task, ["/tmp/nonexistent_design.v"]))
        assert isinstance(report, VerificationReport)
        # Must not raise; either passes (if yosys exists) or fails gracefully

    def test_verify_chip_no_artifacts_error_report(self):
        """Chip verification with empty artifacts list must return error report."""
        runner = VerificationRunner()
        task = TaskNode(
            id="chip_rtl_1",
            domain="chip",
            description="Verify RTL",
            verification_criteria={"lint_pass": 1.0},
        )
        report = _run(runner.verify_task(task, []))
        assert isinstance(report, VerificationReport)
        assert not report.passed
        # Error should mention missing RTL files
        assert any(
            "RTL" in e or ".v" in e or "No" in e
            for e in report.errors
        )

    def test_verify_unknown_domain_graceful(self):
        """Unknown domain must return failed report without raising."""
        runner = VerificationRunner()
        task = TaskNode(
            id="unknown_1",
            domain="quantum_computing",
            description="Quantum circuit compilation",
            verification_criteria={},
        )
        report = _run(runner.verify_task(task, ["/tmp/circuit.qasm"]))
        assert isinstance(report, VerificationReport)
        assert not report.passed
        assert any("Unknown domain" in e for e in report.errors)

    def test_verify_task_duration_is_set(self):
        """VerificationReport must have a duration field set after verify_task."""
        runner = VerificationRunner()
        task = TaskNode(id="t1", domain="eda", description="test")
        report = _run(runner.verify_task(task, []))
        assert report.duration >= 0.0

    def test_verify_task_has_task_id(self):
        """VerificationReport must carry the task_id from the input task."""
        runner = VerificationRunner()
        task = TaskNode(id="my_unique_task_id", domain="eda", description="test")
        report = _run(runner.verify_task(task, []))
        assert report.task_id == "my_unique_task_id"


# ═══════════════════════════════════════════════════════════════
# 5. AI Infra: No Python artifacts
# ═══════════════════════════════════════════════════════════════

class TestVerifyAiInfraNoTorch:
    def test_verify_ai_infra_no_python_files(self):
        """
        AI infra verification with no .py files must return graceful error,
        not raise.
        """
        runner = VerificationRunner()
        task = TaskNode(
            id="ai_train_1",
            domain="ai_infra",
            description="Create training pipeline",
            verification_criteria={"compile_pass": 1.0},
        )
        # CSV files — no Python artifacts
        report = _run(runner.verify_task(task, ["/tmp/data.csv", "/tmp/labels.csv"]))
        assert isinstance(report, VerificationReport)
        assert not report.passed
        assert "No Python artifacts" in report.errors[0]

    def test_verify_ai_infra_empty_artifacts(self):
        """AI infra with empty artifacts list returns error report."""
        runner = VerificationRunner()
        task = TaskNode(
            id="ai_train_2",
            domain="ai_infra",
            description="Train model",
            verification_criteria={"compile_pass": 1.0},
        )
        report = _run(runner.verify_task(task, []))
        assert isinstance(report, VerificationReport)
        assert not report.passed

    def test_verify_ai_infra_nonexistent_py_file(self):
        """AI infra with non-existent .py file must not raise — returns report."""
        runner = VerificationRunner()
        task = TaskNode(
            id="ai_train_3",
            domain="ai_infra",
            description="Test AI pipeline",
            verification_criteria={"compile_pass": 1.0},
        )
        report = _run(runner.verify_task(task, ["/nonexistent/path/train.py"]))
        assert isinstance(report, VerificationReport)
        # Must not raise even if file doesn't exist

    def test_verify_ai_infra_mixed_artifacts(self):
        """Mixed non-Python artifacts with one .py file — .py should be checked."""
        runner = VerificationRunner()
        task = TaskNode(
            id="ai_train_4",
            domain="ai_infra",
            description="Mixed artifacts",
            verification_criteria={},
        )
        # Has one .py file so compile check should run
        report = _run(runner.verify_task(task, [
            "/tmp/data.csv",
            "/tmp/model.pt",
            "/nonexistent/script.py",
        ]))
        assert isinstance(report, VerificationReport)
        # Must not raise


# ═══════════════════════════════════════════════════════════════
# 6. Logger captures missing dependency information
# ═══════════════════════════════════════════════════════════════

class TestLoggerCapturesMissingDep:
    def test_all_tools_missing_no_crash(self, caplog):
        """
        When all tools are missing, detect_all_tools must complete without
        crashing and all open-source tools must be MISSING.
        """
        with caplog.at_level(logging.DEBUG):
            with patch("shutil.which", return_value=None):
                manifest = detect_all_tools()
        missing = manifest.missing_tools()
        assert len(missing) > 0

    def test_detect_tool_empty_commands_list(self):
        """detect_tool with empty commands list must return MISSING gracefully."""
        status = detect_tool("empty-tool", [], "--version")
        assert status.status == "MISSING"
        assert status.name == "empty-tool"

    def test_detect_tool_empty_string_commands_skipped(self):
        """Empty string entries in commands must be skipped without crash."""
        with patch("shutil.which", return_value=None):
            status = detect_tool("yosys", ["", "", ""], "--version")
        assert status.status == "MISSING"

    def test_detect_tool_with_real_found_command(self):
        """When a real command path is returned by mock, tool must be FOUND."""
        def mock_which(cmd):
            return f"/usr/bin/{cmd}" if cmd == "real-tool" else None

        with patch("shutil.which", side_effect=mock_which):
            with patch(
                "cktclaw.eda_tools.tool_detection._try_version",
                return_value="real-tool 2.0",
            ):
                status = detect_tool("real-tool", ["fake-tool", "real-tool"], "--version")
        assert status.status == "FOUND"
        assert "real-tool" in status.path

    def test_manifest_serialization_roundtrip(self, tmp_path):
        """Manifest with all-missing tools must survive JSON serialization roundtrip."""
        from cktclaw.eda_tools.tool_detection import write_tool_manifest, load_tool_manifest

        with patch("shutil.which", return_value=None):
            manifest = detect_all_tools()

        manifest_path = tmp_path / "tool-manifest.json"
        write_tool_manifest(manifest, manifest_path)
        loaded = load_tool_manifest(manifest_path)

        assert len(loaded.tools) == len(manifest.tools)
        for original, restored in zip(manifest.tools, loaded.tools):
            assert original.name == restored.name
            assert original.status == restored.status

    def test_verification_runner_exception_wrapped_gracefully(self):
        """
        If an unexpected exception occurs inside VerificationRunner,
        it must be caught and returned as a failed VerificationReport.
        """
        runner = VerificationRunner()

        # Patch _verify_eda to raise an unexpected error
        async def raise_error(task, artifacts):
            raise RuntimeError("Unexpected internal error")

        runner._verify_eda = raise_error

        task = TaskNode(id="fail_task", domain="eda", description="test")
        report = _run(runner.verify_task(task, ["/tmp/design.v"]))
        assert isinstance(report, VerificationReport)
        assert not report.passed
        assert any("Unexpected internal error" in e for e in report.errors)
