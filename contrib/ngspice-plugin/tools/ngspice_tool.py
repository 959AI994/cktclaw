"""
ngspice Tool — SPICE circuit simulation.
"""

import asyncio
import os
import tempfile
from typing import Any, Dict

from cktclaw.tools.base import BaseTool, ToolContext, ToolResult


class NgspiceTool(BaseTool):
    """Run SPICE circuit simulations using ngspice."""

    name = "ngspice"
    description = (
        "Run SPICE circuit simulations using ngspice. "
        "Supports DC, AC, transient analysis, Monte Carlo, "
        "and parameter sweeps. Input: SPICE netlist (.spice/.cir)."
    )
    parameters = {
        "type": "object",
        "properties": {
            "command": {
                "type": "string",
                "description": (
                    "ngspice command or script to execute. Can be inline SPICE "
                    "directives or a path to a .spice/.cir file."
                ),
            },
            "netlist_file": {
                "type": "string",
                "description": "Path to SPICE netlist file (.spice, .cir)",
            },
            "analysis_type": {
                "type": "string",
                "enum": ["dc", "ac", "tran", "op", "noise", "monte_carlo"],
                "description": "Type of SPICE analysis to run",
            },
            "output_format": {
                "type": "string",
                "enum": ["raw", "csv", "text"],
                "description": "Output format (default: text)",
            },
        },
        "required": ["command"],
    }
    read_only = False
    category = "eda"
    requires = ["ngspice"]

    async def execute(self, params: Dict[str, Any], context: ToolContext) -> ToolResult:
        """Execute ngspice simulation."""
        command = params.get("command", "")
        netlist_file = params.get("netlist_file")

        ngspice_path = self._find_ngspice()
        if not ngspice_path:
            return ToolResult.fail(
                "ngspice not found. Install: apt install ngspice"
            )

        try:
            if netlist_file:
                cmd = [ngspice_path, "-b", netlist_file]
            else:
                # Write inline commands to temp file
                with tempfile.NamedTemporaryFile(
                    mode="w", suffix=".spice", delete=False
                ) as f:
                    f.write(command)
                    if not command.strip().endswith(".endc"):
                        f.write("\n.end\n")
                    temp_path = f.name
                cmd = [ngspice_path, "-b", temp_path]

            working_dir = context.working_dir or os.getcwd()

            proc = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                cwd=working_dir,
            )
            stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=120)

            if not netlist_file:
                os.unlink(temp_path)

            stdout_str = stdout.decode("utf-8", errors="replace")
            stderr_str = stderr.decode("utf-8", errors="replace")

            if proc.returncode == 0:
                return ToolResult.ok(output=stdout_str or stderr_str)
            else:
                return ToolResult.fail(
                    error=f"ngspice exited with code {proc.returncode}",
                    output=stderr_str or stdout_str,
                )

        except asyncio.TimeoutError:
            return ToolResult.fail("ngspice execution timed out (120s limit)")
        except Exception as e:
            return ToolResult.fail(f"ngspice error: {str(e)}")

    def _find_ngspice(self) -> str:
        import shutil
        return shutil.which("ngspice") or ""
