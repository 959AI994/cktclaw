"""
Verible Tool - SystemVerilog linting and formatting.

Wraps the Verible command line tools with the BaseTool interface.
"""

import asyncio
import os
import shlex
from pathlib import Path
from typing import Any, Dict, List

from ..base import BaseTool, ToolContext, ToolResult


class VeribleTool(BaseTool):
    """Run Verible lint or formatter on Verilog/SystemVerilog files."""

    name = "verible"
    description = (
        "Run Verible SystemVerilog linting or formatting. Use it to enforce "
        "style rules, catch common RTL issues, and format Verilog/SystemVerilog "
        "before simulation, synthesis, or review."
    )
    parameters = {
        "type": "object",
        "properties": {
            "action": {
                "type": "string",
                "enum": ["lint", "format"],
                "description": "Run the linter or formatter.",
            },
            "files": {
                "type": "array",
                "items": {"type": "string"},
                "description": "Verilog/SystemVerilog files to analyze.",
            },
            "extra_args": {
                "type": "string",
                "description": "Additional Verible CLI flags, split with shell-like quoting.",
            },
            "inplace": {
                "type": "boolean",
                "description": "For format action, rewrite files in place.",
            },
        },
        "required": ["action", "files"],
    }
    read_only = False
    category = "eda"
    requires = ["verible"]

    async def execute(self, params: Dict[str, Any], context: ToolContext) -> ToolResult:
        action = params.get("action", "lint")
        files = params.get("files") or []
        if isinstance(files, str):
            files = [files]
        if not files:
            return ToolResult.fail("No Verilog/SystemVerilog files provided.")

        exe = self._find_executable(action)
        if not exe:
            return ToolResult.fail(
                "Verible not found. Install oss-cad-suite or Verible binaries "
                "(verible-verilog-lint/verible-verilog-format)."
            )

        args: List[str] = [exe]
        if action == "format" and params.get("inplace", False):
            args.append("--inplace")

        extra_args = params.get("extra_args") or ""
        if extra_args:
            args.extend(shlex.split(extra_args))
        args.extend(str(f) for f in files)

        return await self._run(args, context)

    async def _run(self, args: List[str], context: ToolContext) -> ToolResult:
        try:
            proc = await asyncio.create_subprocess_exec(
                *args,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                cwd=context.working_dir or os.getcwd(),
            )
            stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=120)
            out = stdout.decode("utf-8", errors="replace")
            err = stderr.decode("utf-8", errors="replace")
            combined = "\n".join(p for p in [out, err] if p).strip()
            if proc.returncode == 0:
                return ToolResult.ok(
                    output=combined or "Verible completed successfully.",
                    metadata={"returncode": 0, "command": args},
                )
            return ToolResult.fail(
                error=f"Verible exited with code {proc.returncode}",
                output=combined,
                metadata={"returncode": proc.returncode, "command": args},
            )
        except asyncio.TimeoutError:
            return ToolResult.fail("Verible execution timed out (120s limit)")
        except Exception as e:
            return ToolResult.fail(f"Verible execution error: {e}")

    def _find_executable(self, action: str) -> str:
        import shutil

        exe_name = "verible-verilog-format" if action == "format" else "verible-verilog-lint"
        path = shutil.which(exe_name)
        if path:
            return path
        for candidate in [
            Path("/usr/bin") / exe_name,
            Path("/usr/local/bin") / exe_name,
        ]:
            if candidate.is_file() and os.access(candidate, os.X_OK):
                return str(candidate)
        return ""
