"""
OpenROAD Tool — physical design (place & route) via OpenROAD.

NEW tool implementing full P&R flow integration.
"""

import asyncio
import os
import tempfile
from pathlib import Path
from typing import Any, Dict

from ..base import BaseTool, ToolContext, ToolResult


class OpenROADTool(BaseTool):
    """Physical design using OpenROAD (floorplan, placement, CTS, routing)."""

    name = "openroad"
    description = (
        "Run OpenROAD physical design operations. Supports floorplanning, "
        "global/detailed placement, clock tree synthesis (CTS), "
        "global/detailed routing, timing/power/area reporting, and DEF/GDS output. "
        "Input: gate-level netlist (Verilog) + Liberty (.lib) + LEF + SDC constraints."
    )
    parameters = {
        "type": "object",
        "properties": {
            "command": {
                "type": "string",
                "description": (
                    "OpenROAD TCL command(s) to execute. Examples: "
                    "'read_lef tech.lef; read_def design.def; detailed_placement; write_def out.def', "
                    "'initialize_floorplan -die_area {0 0 100 100} -core_area {10 10 90 90}'"
                ),
            },
            "operation": {
                "type": "string",
                "enum": [
                    "floorplan", "place", "cts", "route",
                    "report_timing", "report_power", "report_area",
                    "write_def", "write_gds", "custom"
                ],
                "description": "High-level operation to perform (alternative to raw TCL)",
            },
            "input_def": {
                "type": "string",
                "description": "Path to input DEF file",
            },
            "input_verilog": {
                "type": "string",
                "description": "Path to gate-level netlist",
            },
            "liberty_file": {
                "type": "string",
                "description": "Path to Liberty timing library (.lib)",
            },
            "lef_file": {
                "type": "string",
                "description": "Path to LEF technology/cell library file",
            },
            "sdc_file": {
                "type": "string",
                "description": "Path to SDC timing constraints",
            },
            "output_file": {
                "type": "string",
                "description": "Path for output file (DEF, GDS, or report)",
            },
        },
        "required": ["command"],
    }
    read_only = False
    category = "eda"
    requires = ["openroad"]

    async def execute(self, params: Dict[str, Any], context: ToolContext) -> ToolResult:
        """Execute OpenROAD physical design command."""
        command = params.get("command", "")
        operation = params.get("operation", "custom")

        openroad_path = self._find_openroad()
        if not openroad_path:
            return ToolResult.fail(
                "OpenROAD not found. Install via: "
                "https://github.com/The-OpenROAD-Project/OpenROAD"
            )

        try:
            # Build TCL script from high-level operation or raw command
            tcl_script = self._build_tcl(params, operation, command)

            # Write to temp file
            with tempfile.NamedTemporaryFile(
                mode="w", suffix=".tcl", delete=False
            ) as f:
                f.write(tcl_script)
                tcl_path = f.name

            working_dir = context.working_dir or os.getcwd()

            proc = await asyncio.create_subprocess_exec(
                openroad_path, "-exit", tcl_path,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                cwd=working_dir,
            )
            stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=300)

            os.unlink(tcl_path)

            stdout_str = stdout.decode("utf-8", errors="replace")
            stderr_str = stderr.decode("utf-8", errors="replace")

            if proc.returncode == 0:
                return ToolResult.ok(
                    output=stdout_str,
                    metadata={
                        "returncode": 0,
                        "operation": operation,
                    },
                )
            else:
                return ToolResult.fail(
                    error=f"OpenROAD exited with code {proc.returncode}",
                    output=stderr_str or stdout_str,
                )

        except asyncio.TimeoutError:
            return ToolResult.fail("OpenROAD execution timed out (300s limit)")
        except Exception as e:
            return ToolResult.fail(f"OpenROAD execution error: {str(e)}")

    def _build_tcl(self, params: Dict, operation: str, command: str) -> str:
        """Build TCL script from parameters."""
        lines = []

        # Load design files if provided
        lef_file = params.get("lef_file")
        if lef_file:
            lines.append(f"read_lef {lef_file}")

        liberty_file = params.get("liberty_file")
        if liberty_file:
            lines.append(f"read_liberty {liberty_file}")

        input_verilog = params.get("input_verilog")
        if input_verilog:
            lines.append(f"read_verilog {input_verilog}")

        input_def = params.get("input_def")
        if input_def:
            lines.append(f"read_def {input_def}")

        sdc_file = params.get("sdc_file")
        if sdc_file:
            lines.append(f"read_sdc {sdc_file}")

        # Add the main command
        if operation == "custom" or not operation:
            lines.append(command)
        else:
            lines.append(command)

        # Output handling
        output_file = params.get("output_file")
        if output_file:
            if output_file.endswith(".def"):
                lines.append(f"write_def {output_file}")
            elif output_file.endswith(".gds"):
                lines.append(f"write_gds {output_file}")

        lines.append("exit")
        return "\n".join(lines)

    def _find_openroad(self) -> str:
        """Find the OpenROAD binary."""
        import shutil
        path = shutil.which("openroad")
        if path:
            return path
        # Check common build locations
        for candidate in [
            "/usr/local/bin/openroad",
            os.path.expanduser("~/OpenROAD/build/src/openroad"),
        ]:
            if os.path.isfile(candidate) and os.access(candidate, os.X_OK):
                return candidate
        return ""
