"""
Wolvrix Tool - SystemVerilog IR transforms through GRH.
"""

import asyncio
import importlib.util
import os
from pathlib import Path
from typing import Any, Dict, List

from ..base import BaseTool, ToolContext, ToolResult


class WolvrixTool(BaseTool):
    """Run Wolvrix Python API for SV parsing, GRH passes, and emission."""

    name = "wolvrix"
    description = (
        "Run Wolvrix to parse SystemVerilog into GRH IR, execute transform or "
        "analysis passes, and emit JSON or rewritten SystemVerilog. Useful for "
        "structure-aware RTL refactoring and agent-driven transformations."
    )
    parameters = {
        "type": "object",
        "properties": {
            "input_file": {
                "type": "string",
                "description": "SystemVerilog source file to read.",
            },
            "top": {
                "type": "string",
                "description": "Optional top module passed to slang.",
            },
            "passes": {
                "type": "array",
                "items": {"type": "string"},
                "description": "Wolvrix passes to run, e.g. xmr-resolve, simplify, stats.",
            },
            "output_json": {
                "type": "string",
                "description": "Optional JSON output path for the transformed design.",
            },
            "output_sv": {
                "type": "string",
                "description": "Optional SystemVerilog output path for emitted design.",
            },
        },
        "required": ["input_file"],
    }
    read_only = False
    category = "eda"
    requires = ["wolvrix"]

    async def execute(self, params: Dict[str, Any], context: ToolContext) -> ToolResult:
        if importlib.util.find_spec("wolvrix") is None:
            return ToolResult.fail(
                "wolvrix Python package not found. Install Wolf-Tungsten/wolvrix first."
            )

        input_file = params.get("input_file")
        if not input_file:
            return ToolResult.fail("Missing input_file.")

        try:
            result = await asyncio.to_thread(self._run_wolvrix, params, context)
            return ToolResult.ok(
                output=result["output"],
                metadata=result["metadata"],
                artifacts=result["artifacts"],
            )
        except Exception as e:
            return ToolResult.fail(f"Wolvrix execution error: {e}")

    def _run_wolvrix(self, params: Dict[str, Any], context: ToolContext) -> Dict[str, Any]:
        import wolvrix

        input_file = str(params["input_file"])
        top = params.get("top")
        passes: List[str] = list(params.get("passes") or [])
        output_json = params.get("output_json")
        output_sv = params.get("output_sv")

        cwd = Path(context.working_dir or os.getcwd())
        slang_args = ["--top", str(top)] if top else []
        artifacts: List[str] = []
        logs: List[str] = []

        with wolvrix.Session() as sess:
            sess.log_level = "info"
            sess.diagnostics_print_min_level = "warning"
            sess.diagnostics_raise_min_level = "error"
            sess.read_sv(input_file, out_design="design.main", slang_args=slang_args)
            logs.append(f"read_sv: {input_file}")

            for pass_name in passes:
                kwargs: Dict[str, Any] = {"design": "design.main"}
                if pass_name == "stats":
                    kwargs["out_stats"] = "stats.main"
                sess.run_pass(pass_name, **kwargs)
                logs.append(f"run_pass: {pass_name}")

            if output_json:
                out = str((cwd / output_json).resolve() if not os.path.isabs(output_json) else output_json)
                sess.store_json(design="design.main", output=out)
                artifacts.append(out)
                logs.append(f"store_json: {out}")
            if output_sv:
                out = str((cwd / output_sv).resolve() if not os.path.isabs(output_sv) else output_sv)
                sess.emit_sv(design="design.main", output=out)
                artifacts.append(out)
                logs.append(f"emit_sv: {out}")

        return {
            "output": "\n".join(logs) or "Wolvrix completed successfully.",
            "metadata": {
                "input_file": input_file,
                "top": top,
                "passes": passes,
            },
            "artifacts": artifacts,
        }
