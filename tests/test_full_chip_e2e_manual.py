"""Manual E2E gate tests — fixture + doctor only; no live DeepSeek calls in CI."""

from __future__ import annotations

import shutil
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
FIXTURE = ROOT / "tests" / "fixtures" / "full_chip_e2e" / "workspace"
REPORT = ROOT / "tests" / "e2e_reports"


@pytest.mark.e2e_live
def test_e2e_fixtures_exist():
    assert (FIXTURE / "bad_counter.v").is_file()
    assert (FIXTURE / "broken_fifo.v").is_file()
    assert (FIXTURE / "top.sv").is_file()
    assert (FIXTURE / "include" / "defs.svh").is_file()


@pytest.mark.e2e_live
def test_e2e_preflight_baseline_written():
    """After scripts/run_e2e_preflight.sh, baseline markdown should exist."""
    baselines = sorted(REPORT.glob("*_baseline.md"))
    if not baselines:
        pytest.skip("Run scripts/run_e2e_preflight.sh first")
    text = baselines[-1].read_text(encoding="utf-8")
    assert "agent_repos" in text.lower() or "Doctor Checks" in text


@pytest.mark.e2e_live
def test_e2e_workspace_deployable(tmp_path):
    ws = tmp_path / "workspace"
    for src in FIXTURE.rglob("*"):
        if src.is_file():
            rel = src.relative_to(FIXTURE)
            dst = ws / rel
            dst.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(src, dst)
    assert (ws / "bad_counter.v").is_file()


@pytest.mark.e2e_live
def test_bad_counter_fails_verilator_lint(tmp_path):
    verilator = shutil.which("verilator")
    if not verilator:
        pytest.skip("verilator not on PATH")
    import subprocess

    src = FIXTURE / "bad_counter.v"
    proc = subprocess.run(
        [verilator, "--lint-only", str(src)],
        capture_output=True,
        text=True,
    )
    # Expect lint/elab issues (non-zero or warnings in output)
    combined = proc.stdout + proc.stderr
    assert proc.returncode != 0 or "error" in combined.lower() or "warn" in combined.lower()


def test_e2e_live_marker_registered():
    assert hasattr(pytest.mark, "e2e_live")
