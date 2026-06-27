#!/usr/bin/env python3
"""Minimal stdio MCP server for one CktClaw chip EDA tool."""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import tool_runtime  # noqa: E402


def _send(message: dict) -> None:
    sys.stdout.write(json.dumps(message, separators=(",", ":")) + "\n")
    sys.stdout.flush()


def _ok(request_id, result: dict) -> dict:
    return {"jsonrpc": "2.0", "id": request_id, "result": result}


def _err(request_id, code: int, message: str) -> dict:
    return {"jsonrpc": "2.0", "id": request_id, "error": {"code": code, "message": message}}


def _input_schema() -> dict:
    return {
        "type": "object",
        "properties": {
            "args": {"type": "array", "items": {"type": "string"}, "default": []},
            "command": {"type": "string"},
            "script": {"type": "string"},
            "script_file": {"type": "string"},
            "tcl_script": {"type": "string"},
            "netlist_file": {"type": "string"},
            "working_dir": {"type": "string"},
            "timeout_s": {"type": "integer"},
            "root": {"type": "string"},
            "env": {"type": "object", "additionalProperties": {"type": "string"}},
        },
    }


def _tool_descriptor(tool: str) -> dict:
    spec = tool_runtime.TOOL_SPECS[tool]
    return {
        "name": f"cktclaw_{tool}",
        "description": spec["description"],
        "inputSchema": _input_schema(),
    }


def serve(tool: str) -> int:
    if tool not in tool_runtime.TOOL_SPECS:
        print(f"Unsupported tool: {tool}", file=sys.stderr)
        return 2

    for line in sys.stdin:
        if not line.strip():
            continue
        try:
            request = json.loads(line)
        except json.JSONDecodeError:
            _send(_err(None, -32700, "Invalid JSON"))
            continue

        request_id = request.get("id")
        method = request.get("method")
        params = request.get("params") or {}

        try:
            if method == "initialize":
                _send(
                    _ok(
                        request_id,
                        {
                            "protocolVersion": "2024-11-05",
                            "serverInfo": {"name": f"cktclaw-{tool}", "version": "0.1.0"},
                            "capabilities": {"tools": {}},
                        },
                    )
                )
            elif method == "tools/list":
                _send(_ok(request_id, {"tools": [_tool_descriptor(tool)]}))
            elif method == "tools/call":
                arguments = params.get("arguments") or {}
                arguments.setdefault("root", os.environ.get("CKTCLAW_CHIP_ROOT", ""))
                if "timeout_s" not in arguments and os.environ.get("TOOL_TIMEOUT_S"):
                    arguments["timeout_s"] = int(os.environ["TOOL_TIMEOUT_S"])
                result = tool_runtime.run_tool(tool, arguments)
                _send(_ok(request_id, {"content": [{"type": "text", "text": json.dumps(result, indent=2)}]}))
            else:
                _send(_err(request_id, -32601, f"Unknown method: {method}"))
        except Exception as exc:
            _send(_err(request_id, -32000, str(exc)))
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--tool", required=True, choices=sorted(tool_runtime.TOOL_SPECS))
    args = parser.parse_args()
    return serve(args.tool)


if __name__ == "__main__":
    raise SystemExit(main())
