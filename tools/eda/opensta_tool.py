"""
OpenSTA Tool — static timing analysis via OpenSTA.

Wraps the existing opensta_runner.py with the BaseTool interface.
"""

import asyncio
import os
import tempfile
from pathlib import Path
from typing import Any, Dict

from ..base import BaseTool, ToolContext, ToolResult


class OpenSTATool(BaseTool):
    """Static timing analysis using OpenSTA."""

    name = "opensta"
    description = (
        "Run static timing analysis (STA) using OpenSTA. "
        "Analyze timing paths, check setup/hold violations, "
        "report slack, generate timing reports for gate-level designs."
    )
    parameters = {
        "type": "object",
        "properties": {
            "command": {
                "type": "string",
                "description": (
                    "OpenSTA TCL command to execute. Examples: "
                    "'read_liberty lib.lib; read_verilog netlist.v; link_design top; "
                    "read_sdc constraints.sdc; report_checks'"
                ),
            },
            "netlist_file": {
                "type": "string",
                "description": "Path to gate-level netlist (Verilog)",
            },
            "liberty_file": {
                "type": "string",
                "description": "Path to Liberty (.lib) timing library",
            },
            "sdc_file": {
                "type": "string",
                "description": "Path to SDC constraints file",
            },
            "report_type": {
                "type": "string",
                "enum": ["checks", "worst_slack", "tns", "all_violators", "clock_skew"],
                "description": "Type of timing report to generate",
            },
        },
        "required": ["command"],
    }
    read_only = True  # STA is read-only analysis
    category = "eda"
    requires = ["opensta"]

    async def execute(self, params: Dict[str, Any], context: ToolContext) -> ToolResult:
        """Execute OpenSTA timing analysis."""
        command = params.get("command", "")

        sta_path = self._find_opensta()
        if not sta_path:
            return ToolResult.fail("OpenSTA not found. Build from source or install via setup.sh")

        try:
            # Write TCL script to temp file
            with tempfile.NamedTemporaryFile(
                mode="w", suffix=".tcl", delete=False
            ) as f:
                f.write(command)
                if not command.strip().endswith("exit"):
                    f.write("\nexit\n")
                tcl_path = f.name

            working_dir = context.working_dir or os.getcwd()

            proc = await asyncio.create_subprocess_exec(
                sta_path, "-exit", tcl_path,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                cwd=working_dir,
            )
            stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=60)

            # Cleanup temp file
            os.unlink(tcl_path)

            stdout_str = stdout.decode("utf-8", errors="replace")
            stderr_str = stderr.decode("utf-8", errors="replace")

            if proc.returncode == 0:
                return ToolResult.ok(
                    output=stdout_str,
                    metadata={"returncode": 0},
                )
            else:
                return ToolResult.fail(
                    error=f"OpenSTA exited with code {proc.returncode}",
                    output=stderr_str or stdout_str,
                )

        except asyncio.TimeoutError:
            return ToolResult.fail("OpenSTA execution timed out (60s limit)")
        except Exception as e:
            return ToolResult.fail(f"OpenSTA execution error: {str(e)}")

    def _find_opensta(self) -> str:
        """Find the OpenSTA binary."""
        import shutil
        # Check env var first
        env_path = os.environ.get("OPENSTA_PATH", "")
        if env_path and os.path.isfile(env_path):
            return env_path
        path = shutil.which("sta")
        if path:
            return path
        return ""
