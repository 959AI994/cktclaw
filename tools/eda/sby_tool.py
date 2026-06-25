"""
SymbiYosys Tool - formal verification through sby.
"""

import asyncio
import os
import shlex
import tempfile
from pathlib import Path
from typing import Any, Dict, List

from ..base import BaseTool, ToolContext, ToolResult


class SbyTool(BaseTool):
    """Run SymbiYosys jobs for formal verification."""

    name = "sby"
    description = (
        "Run SymbiYosys (sby) formal verification jobs. Use it for BMC, prove, "
        "cover, and live property checks backed by Yosys-compatible engines."
    )
    parameters = {
        "type": "object",
        "properties": {
            "sby_file": {
                "type": "string",
                "description": "Path to an existing .sby job file.",
            },
            "sby_content": {
                "type": "string",
                "description": "Inline .sby job content. Written to a temporary job file.",
            },
            "mode": {
                "type": "string",
                "enum": ["bmc", "prove", "cover", "live", "default"],
                "description": "Optional mode override passed as --mode.",
            },
            "workdir": {
                "type": "string",
                "description": "Optional SymbiYosys output directory.",
            },
            "extra_args": {
                "type": "string",
                "description": "Additional sby CLI flags, split with shell-like quoting.",
            },
        },
        "required": [],
    }
    read_only = False
    category = "eda"
    requires = ["symbiyosys"]

    async def execute(self, params: Dict[str, Any], context: ToolContext) -> ToolResult:
        exe = self._find_sby()
        if not exe:
            return ToolResult.fail("SymbiYosys not found. Install oss-cad-suite or sby.")

        job_file = params.get("sby_file")
        temp_path = None
        if not job_file and params.get("sby_content"):
            temp_path = self._write_temp_job(params["sby_content"], context)
            job_file = temp_path
        if not job_file:
            return ToolResult.fail("Provide either 'sby_file' or 'sby_content'.")

        args: List[str] = [exe]
        mode = params.get("mode")
        if mode and mode != "default":
            args.extend(["--mode", str(mode)])
        workdir = params.get("workdir")
        if workdir:
            args.extend(["--prefix", str(workdir)])
        extra_args = params.get("extra_args") or ""
        if extra_args:
            args.extend(shlex.split(extra_args))
        args.append(str(job_file))

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
                    output=combined or "SymbiYosys completed successfully.",
                    metadata={"returncode": 0, "command": args},
                )
            return ToolResult.fail(
                error=f"SymbiYosys exited with code {proc.returncode}",
                output=combined,
                metadata={"returncode": proc.returncode, "command": args},
            )
        except asyncio.TimeoutError:
            return ToolResult.fail("SymbiYosys execution timed out (600s limit)")
        except Exception as e:
            return ToolResult.fail(f"SymbiYosys execution error: {e}")
        finally:
            if temp_path:
                try:
                    Path(temp_path).unlink(missing_ok=True)
                except Exception:
                    pass

    def _write_temp_job(self, content: str, context: ToolContext) -> str:
        base_dir = context.working_dir or os.getcwd()
        with tempfile.NamedTemporaryFile(
            mode="w",
            suffix=".sby",
            delete=False,
            dir=base_dir,
            encoding="utf-8",
        ) as f:
            f.write(content)
            return f.name

    def _find_sby(self) -> str:
        import shutil

        return shutil.which("sby") or ""
