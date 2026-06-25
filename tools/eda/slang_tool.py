"""
Slang Tool - SystemVerilog compilation and diagnostics.
"""

import asyncio
import os
import shlex
from typing import Any, Dict, List

from ..base import BaseTool, ToolContext, ToolResult


class SlangTool(BaseTool):
    """Run slang for SystemVerilog parsing, elaboration, and diagnostics."""

    name = "slang"
    description = (
        "Run slang SystemVerilog compiler checks. Use it for fast syntax, "
        "elaboration, type, include, define, and top-module diagnostics before "
        "simulation, formal, or synthesis."
    )
    parameters = {
        "type": "object",
        "properties": {
            "files": {
                "type": "array",
                "items": {"type": "string"},
                "description": "Verilog/SystemVerilog source files.",
            },
            "top": {
                "type": "string",
                "description": "Optional top module name.",
            },
            "include_dirs": {
                "type": "array",
                "items": {"type": "string"},
                "description": "Include directories passed as -I<dir>.",
            },
            "defines": {
                "type": "array",
                "items": {"type": "string"},
                "description": "Preprocessor defines passed as -D<name>[=value].",
            },
            "extra_args": {
                "type": "string",
                "description": "Additional slang CLI flags, split with shell-like quoting.",
            },
        },
        "required": ["files"],
    }
    read_only = True
    category = "eda"
    requires = ["slang"]

    async def execute(self, params: Dict[str, Any], context: ToolContext) -> ToolResult:
        files = params.get("files") or []
        if isinstance(files, str):
            files = [files]
        if not files:
            return ToolResult.fail("No SystemVerilog files provided.")

        exe = self._find_slang()
        if not exe:
            return ToolResult.fail(
                "slang not found. Install slang or oss-cad-suite and ensure 'slang' is on PATH."
            )

        args: List[str] = [exe]
        top = params.get("top")
        if top:
            args.extend(["--top", str(top)])
        for inc in params.get("include_dirs") or []:
            args.append(f"-I{inc}")
        for define in params.get("defines") or []:
            args.append(f"-D{define}")
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
            stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=120)
            out = stdout.decode("utf-8", errors="replace")
            err = stderr.decode("utf-8", errors="replace")
            combined = "\n".join(p for p in [out, err] if p).strip()
            if proc.returncode == 0:
                return ToolResult.ok(
                    output=combined or "slang completed successfully.",
                    metadata={"returncode": 0, "command": args},
                )
            return ToolResult.fail(
                error=f"slang exited with code {proc.returncode}",
                output=combined,
                metadata={"returncode": proc.returncode, "command": args},
            )
        except asyncio.TimeoutError:
            return ToolResult.fail("slang execution timed out (120s limit)")
        except Exception as e:
            return ToolResult.fail(f"slang execution error: {e}")

    def _find_slang(self) -> str:
        import shutil

        return shutil.which("slang") or ""
