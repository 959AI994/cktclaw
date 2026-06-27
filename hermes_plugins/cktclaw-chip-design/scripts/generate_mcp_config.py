#!/usr/bin/env python3
"""Generate Hermes mcp_servers entries for chip EDA tools."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import tool_runtime  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", default=None, help="Toolchain root")
    parser.add_argument("--tool", action="append", dest="tools", help="Tool to expose. Repeatable.")
    parser.add_argument("--output", default=None, help="Optional output path")
    parser.add_argument("--json", action="store_true", help="Print metadata wrapper instead of bare mcp_servers snippet")
    args = parser.parse_args()

    config = tool_runtime.mcp_config(args.tools, args.root)
    snippet = {"mcp_servers": config["mcp_servers"]}
    if args.output:
        output = Path(args.output).expanduser()
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(json.dumps(snippet, indent=2), encoding="utf-8")
        config["output_path"] = str(output)

    print(json.dumps(config if args.json else snippet, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
