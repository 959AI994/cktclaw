#!/usr/bin/env python3
"""Print a CktClaw chip plugin doctor report."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import tool_runtime  # noqa: E402


def _markdown(report: dict) -> str:
    lines = [
        "# CktClaw Chip Doctor",
        "",
        f"Root: `{report['root']}`",
        "",
        "## Repositories",
    ]
    for repo in report["repositories"]:
        mark = "OK" if repo["ready"] else "MISSING"
        lines.append(f"- {mark}: {repo['name']} -> `{repo['path']}`")
    lines.append("")
    lines.append("## Tools")
    for tool in report["tools"]:
        mark = "OK" if tool["found"] else "MISSING"
        lines.append(f"- {mark}: {tool['name']} ({tool['category']})")
    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", default=None, help="Toolchain root")
    parser.add_argument("--format", choices=["json", "markdown"], default="json")
    args = parser.parse_args()

    report = tool_runtime.doctor(args.root)
    if args.format == "markdown":
        print(_markdown(report))
    else:
        print(json.dumps(report, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
