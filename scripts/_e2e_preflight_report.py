#!/usr/bin/env python3
"""Write preflight baseline markdown + JSON (called from run_e2e_preflight.sh)."""
from __future__ import annotations

import json
import re
import shutil
import sys
from pathlib import Path


def parse_doctor_checks(text: str) -> dict[str, str]:
    checks: dict[str, str] = {}
    for line in text.splitlines():
        m = re.match(r"^\│\s+(\S+)\s+\│\s+(OK|WARN|FAIL)\s+\│", line)
        if m:
            checks[m.group(1)] = m.group(2).lower()
    return checks


def main() -> None:
    doctor_path = Path(sys.argv[1])
    pytest_path = Path(sys.argv[2])
    date_tag = sys.argv[3]
    which_cktclaw = sys.argv[4]
    conda_cktclaw = sys.argv[5]
    deepseek_set = sys.argv[6]
    report_dir = Path(sys.argv[7])

    doctor_text = doctor_path.read_text(encoding="utf-8", errors="replace")
    pytest_text = pytest_path.read_text(encoding="utf-8", errors="replace")
    checks = parse_doctor_checks(doctor_text)
    passed = re.search(r"(\d+) passed", pytest_text)
    failed = re.search(r"(\d+) failed", pytest_text)

    summary = {
        "date": date_tag,
        "doctor_checks": checks,
        "pytest_passed": int(passed.group(1)) if passed else 0,
        "pytest_failed": int(failed.group(1)) if failed else 0,
        "which_cktclaw": which_cktclaw,
        "conda_cktclaw": conda_cktclaw,
        "deepseek_key_set": deepseek_set == "yes",
        "eda_tools": {
            t: shutil.which(t)
            for t in [
                "yosys", "abc", "sta", "verilator", "sby",
                "verible-verilog-lint", "slang",
            ]
        },
    }
    report_dir.joinpath(f"{date_tag}_preflight.json").write_text(
        json.dumps(summary, indent=2, ensure_ascii=False), encoding="utf-8"
    )

    lines = [
        "# CktClaw E2E Preflight Baseline",
        "",
        f"Date: {date_tag}",
        "",
        "## Environment",
        f"- which cktclaw: {which_cktclaw}",
        f"- conda cktclaw: {conda_cktclaw}",
        f"- DEEPSEEK_API_KEY set: {deepseek_set}",
        "",
        "## Doctor Checks",
    ]
    for name, status in checks.items():
        lines.append(f"- **{name}**: {status}")
    lines.extend([
        "",
        "## Pytest",
        f"- passed: {summary['pytest_passed']}",
        f"- failed: {summary['pytest_failed']}",
        "",
        "## EDA Tools on PATH",
    ])
    for tool, path in summary["eda_tools"].items():
        lines.append(f"- {tool}: {path or 'missing'}")
    lines.extend([
        "",
        "## Raw Doctor Output",
        "",
        doctor_text.strip(),
    ])
    out = report_dir / f"{date_tag}_baseline.md"
    out.write_text("\n".join(lines), encoding="utf-8")
    print(f"Wrote {out}")


if __name__ == "__main__":
    main()
