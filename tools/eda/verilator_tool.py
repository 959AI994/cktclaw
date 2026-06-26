"""
Verilator Tool - linting and simulation compilation.
"""

import asyncio
import os
import shlex
from typing import Any, Dict, List

from ..base import BaseTool, ToolContext, ToolResult


class VerilatorTool(BaseTool):
    """Run Verilator lint and simulation compilation flows."""

    name = "verilator"
    description = (
        "Run Verilator for SystemVerilog linting or C++ simulation compilation. "
        "Use it as a fast pre-synthesis compile gate and as a simulation backend."
    )
    parameters = {
        "type": "object",
        "properties": {
            "action": {
                "type": "string",
                "enum": ["lint", "compile"],
                "description": "Use lint for --lint-only or compile for simulation build.",
            },
            "files": {
                "type": "array",
                "items": {"type": "string"},
                "description": "Verilog/SystemVerilog source files.",
            },
            "top": {
                "type": "string",
                "description": "Optional top module.",
            },
            "include_dirs": {
                "type": "array",
                "items": {"type": "string"},
                "description": "Include directories passed as -I<dir>.",
            },
            "extra_args": {
                "type": "string",
                "description": "Additional Verilator CLI flags, split with shell-like quoting.",
            },
        },
        "required": ["action", "files"],
    }
    read_only = False
    category = "eda"
    requires = ["verilator"]

    async def execute(self, params: Dict[str, Any], context: ToolContext) -> ToolResult:
        files = params.get("files") or []
        if isinstance(files, str):
            files = [files]
        if not files:
            return ToolResult.fail("No Verilog/SystemVerilog files provided.")

        exe = self._find_verilator()
        if not exe:
            return ToolResult.fail("Verilator not found. Install Verilator or oss-cad-suite.")

        action = params.get("action", "lint")
        args: List[str] = [exe, "--sv"]
        if action == "lint":
            args.append("--lint-only")
        else:
            args.extend(["--cc", "--build"])

        top = params.get("top")
        if top:
            args.extend(["--top-module", str(top)])
        for inc in params.get("include_dirs") or []:
            args.append(f"-I{inc}")
        extra_args = params.get("extra_args") or ""
        if extra_args:
            args.extend(shlex.split(extra_args))
        args.extend(str(f) for f in files)

        try:
            proc = await asyncio.create_subprocess_exec(
                *args,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                cwd=context.working_dir or os.getcwd(),
            )
            stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=600)
            out = stdout.decode("utf-8", errors="replace")
            err = stderr.decode("utf-8", errors="replace")
            combined = "\n".join(p for p in [out, err] if p).strip()
            if proc.returncode == 0:
                return ToolResult.ok(
                    output=combined or "Verilator completed successfully.",
                    metadata={"returncode": 0, "command": args},
                )
            return ToolResult.fail(
                error=f"Verilator exited with code {proc.returncode}",
                output=combined,
                metadata={"returncode": proc.returncode, "command": args},
            )
        except asyncio.TimeoutError:
            return ToolResult.fail("Verilator execution timed out (600s limit)")
        except Exception as e:
            return ToolResult.fail(f"Verilator execution error: {e}")

    def _find_verilator(self) -> str:
        import shutil

        return shutil.which("verilator") or ""
