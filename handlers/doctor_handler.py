"""
cktclaw doctor — structured environment health report.

Produces a deterministic set of checks (credentials, EDA tools, run-home
writability, policy validity, offline/provider consistency) with a nonzero
exit code when any check fails. Used for onboarding and CI smoke tests.
"""
from __future__ import annotations

import os
import shutil
from dataclasses import dataclass, field
from pathlib import Path
from typing import List


@dataclass
class DoctorCheck:
    name: str
    status: str  # "ok" | "warn" | "fail"
    detail: str = ""


@dataclass
class DoctorReport:
    checks: List[DoctorCheck] = field(default_factory=list)

    def add(self, name: str, status: str, detail: str = "") -> None:
        self.checks.append(DoctorCheck(name=name, status=status, detail=detail))

    def exit_code(self) -> int:
        return 1 if any(c.status == "fail" for c in self.checks) else 0

    def has_warnings(self) -> bool:
        return any(c.status == "warn" for c in self.checks)


def _check_api_keys() -> DoctorCheck:
    try:
        from ..api_credentials import get_deepseek_api_key
        key = get_deepseek_api_key(required=False)
        if key:
            return DoctorCheck("api_keys", "ok", "DeepSeek key resolved")
        return DoctorCheck("api_keys", "warn",
                           "No DeepSeek key (set DEEPSEEK_API_KEY or use a local model)")
    except Exception as e:
        return DoctorCheck("api_keys", "warn", f"credential check error: {e}")


def _check_eda_tools() -> DoctorCheck:
    tools = ["yosys", "abc", "sta", "verilator"]
    found = {t: shutil.which(t) for t in tools}
    present = [t for t, p in found.items() if p]
    if not present:
        return DoctorCheck("eda_tools", "warn",
                           "no EDA tools found on PATH (yosys/abc/sta/verilator)")
    missing = [t for t in tools if t not in present]
    detail = f"found: {', '.join(present)}"
    if missing:
        detail += f"; missing: {', '.join(missing)}"
    return DoctorCheck("eda_tools", "ok", detail)


def _check_full_chip_toolchain() -> DoctorCheck:
    tools = {
        "verible-lint": "verible-verilog-lint",
        "verible-format": "verible-verilog-format",
        "slang": "slang",
        "symbiyosys": "sby",
        "verilator": "verilator",
        "yosys": "yosys",
        "opensta": "sta",
        "abc": "abc",
    }
    found = [name for name, exe in tools.items() if shutil.which(exe)]
    missing = [name for name in tools if name not in found]
    if not found:
        return DoctorCheck(
            "full_chip_toolchain",
            "warn",
            "no expanded toolchain binaries found; install oss-cad-suite and optional Verible/slang",
        )
    detail = f"found: {', '.join(found)}"
    if missing:
        detail += f"; missing optional: {', '.join(missing)}"
    return DoctorCheck("full_chip_toolchain", "ok", detail)


def _repo_status(name: str, env_var: str, default_path: Path, marker: str) -> str:
    raw = os.environ.get(env_var, "").strip()
    root = Path(raw).expanduser() if raw else default_path
    marker_path = root / marker
    status = "ok" if marker_path.exists() else "missing"
    return f"{name}={status}({root})"


def _check_agent_repos() -> DoctorCheck:
    deps = Path(__file__).resolve().parent.parent / "deps"
    entries = [
        _repo_status(
            "digital-chip-design-agents",
            "CHIP_AGENTS_ROOT",
            deps / "digital-chip-design-agents" / "plugins",
            "synthesis",
        ),
        _repo_status(
            "analog-chip-design-agents",
            "ANALOG_CHIP_AGENTS_ROOT",
            deps / "analog-chip-design-agents" / "plugins",
            "meta",
        ),
        _repo_status(
            "verilog-generator",
            "VERILOG_GENERATOR_ROOT",
            deps / "verilog-generator",
            "SKILL.md",
        ),
        _repo_status(
            "hls-generator",
            "HLS_GENERATOR_ROOT",
            deps / "hls-generator",
            "SKILL.md",
        ),
        _repo_status(
            "RTLFixer",
            "RTLFIXER_ROOT",
            deps / "RTLFixer",
            "src",
        ),
    ]
    missing = [e for e in entries if "=missing" in e]
    status = "warn" if missing else "ok"
    return DoctorCheck("agent_repos", status, "; ".join(entries))


def _check_home_writable() -> DoctorCheck:
    home = os.environ.get("CKTCLAW_HOME")
    root = Path(home) if home else Path.cwd() / ".cktclaw"
    try:
        root.mkdir(parents=True, exist_ok=True)
        probe = root / ".doctor_probe"
        probe.write_text("ok", encoding="utf-8")
        probe.unlink()
        return DoctorCheck("cktclaw_home_writable", "ok", str(root))
    except Exception as e:
        return DoctorCheck("cktclaw_home_writable", "fail", f"{root}: {e}")


def _check_policy() -> DoctorCheck:
    try:
        from ..runtime.permissions import load_policy
        policy = load_policy()
        profiles = policy.get("profiles", {})
        if profiles:
            return DoctorCheck("policy", "ok", f"profiles: {', '.join(profiles)}")
        return DoctorCheck("policy", "warn", "no profiles defined")
    except Exception as e:
        return DoctorCheck("policy", "fail", f"policy load error: {e}")


def _check_offline_consistency() -> DoctorCheck:
    try:
        from ..runtime.data_policy import is_offline
        if is_offline():
            return DoctorCheck("offline_mode", "ok",
                               "offline enabled — cloud egress blocked")
        return DoctorCheck("offline_mode", "ok", "online (cloud egress allowed)")
    except Exception as e:
        return DoctorCheck("offline_mode", "warn", f"offline check error: {e}")


def run_doctor() -> DoctorReport:
    report = DoctorReport()
    report.checks.append(_check_api_keys())
    report.checks.append(_check_eda_tools())
    report.checks.append(_check_full_chip_toolchain())
    report.checks.append(_check_agent_repos())
    report.checks.append(_check_home_writable())
    report.checks.append(_check_policy())
    report.checks.append(_check_offline_consistency())
    return report


def render_doctor(report: DoctorReport, console=None) -> None:
    """Print the report as a Rich table (falls back to plain print)."""
    symbols = {"ok": "[green]OK[/green]", "warn": "[yellow]WARN[/yellow]",
               "fail": "[red]FAIL[/red]"}
    try:
        from rich.table import Table
        from rich.console import Console
        console = console or Console()
        table = Table(title="cktclaw doctor", show_lines=False)
        table.add_column("Check", style="bold")
        table.add_column("Status")
        table.add_column("Detail")
        for c in report.checks:
            table.add_row(c.name, symbols.get(c.status, c.status), c.detail)
        console.print(table)
    except Exception:
        for c in report.checks:
            print(f"[{c.status.upper():>4}] {c.name}: {c.detail}")
