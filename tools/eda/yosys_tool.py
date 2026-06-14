"""
Yosys Tool — logic synthesis via Yosys.

Wraps the existing yosys_runner.py with the BaseTool interface.
"""

import asyncio
import os
import subprocess
import tempfile
from pathlib import Path
from typing import Any, Dict

from ..base import BaseTool, ToolContext, ToolResult


class YosysTool(BaseTool):
    """Logic synthesis using Yosys open synthesis suite."""

    name = "yosys"
    description = (
        "Run Yosys logic synthesis on Verilog/SystemVerilog designs. "
        "Can perform synthesis, technology mapping, optimization, "
        "and generate netlists in various formats."
    )
    parameters = {
        "type": "object",
        "properties": {
            "command": {
                "type": "string",
                "description": (
                    "Yosys TCL/script command to execute. Examples: "
                    "'read_verilog design.v; synth -top module_name; write_verilog out.v', "
                    "'synth_ice40 -top top', 'stat'"
                ),
            },
            "input_file": {
                "type": "string",
                "description": "Path to input Verilog/SystemVerilog file (optional if command includes read)",
            },
            "script_file": {
                "type": "string",
                "description": "Path to Yosys script file to execute (alternative to inline command)",
            },
            "output_format": {
                "type": "string",
                "enum": ["verilog", "json", "blif", "edif", "stat"],
                "description": "Desired output format (default: stat for statistics)",
            },
        },
        "required": ["command"],
    }
    read_only = False
    category = "eda"
    requires = ["yosys"]

    async def execute(self, params: Dict[str, Any], context: ToolContext) -> ToolResult:
        """Execute Yosys synthesis command."""
        command = params.get("command", "")
        input_file = params.get("input_file")
        script_file = params.get("script_file")

        # Find yosys binary
        yosys_path = self._find_yosys()
        if not yosys_path:
            return ToolResult.fail("Yosys not found. Install via: apt install yosys")

        try:
            if script_file:
                # Run script file
                cmd = [yosys_path, "-s", script_file]
            else:
                # Run inline command
                cmd = [yosys_path, "-p", command]

            if input_file:
                cmd.append(input_file)

            working_dir = context.working_dir or os.getcwd()

            proc = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                cwd=working_dir,
            )
            stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=120)

            stdout_str = stdout.decode("utf-8", errors="replace")
            stderr_str = stderr.decode("utf-8", errors="replace")

            if proc.returncode == 0:
                output = stdout_str
                if stderr_str and not stdout_str:
                    output = stderr_str
                return ToolResult.ok(
                    output=output,
                    metadata={"returncode": 0, "command": " ".join(cmd)},
                )
            else:
                return ToolResult.fail(
                    error=f"Yosys exited with code {proc.returncode}",
                    output=stderr_str or stdout_str,
                    metadata={"returncode": proc.returncode},
                )

        except asyncio.TimeoutError:
            return ToolResult.fail("Yosys execution timed out (120s limit)")
        except Exception as e:
            return ToolResult.fail(f"Yosys execution error: {str(e)}")

    def _find_yosys(self) -> str:
        """Find the yosys binary path."""
        import shutil
        path = shutil.which("yosys")
        if path:
            return path
        # Check common locations
        for candidate in ["/usr/bin/yosys", "/usr/local/bin/yosys"]:
            if os.path.isfile(candidate) and os.access(candidate, os.X_OK):
                return candidate
        return ""
