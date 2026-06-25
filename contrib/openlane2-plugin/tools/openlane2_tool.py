"""
OpenLane2 Tool — automated RTL-to-GDS flow.
"""

import asyncio
import os
import json
from typing import Any, Dict

from cktclaw.tools.base import BaseTool, ToolContext, ToolResult


class OpenLane2Tool(BaseTool):
    """Run OpenLane2 automated RTL-to-GDS flow."""

    name = "openlane2"
    description = (
        "Run OpenLane2 for automated RTL-to-GDS-II flow. "
        "Covers synthesis, floorplanning, placement, CTS, routing, "
        "DRC, LVS, and GDSII generation. Requires OpenLane2 installed."
    )
    parameters = {
        "type": "object",
        "properties": {
            "command": {
                "type": "string",
                "description": (
                    "OpenLane2 command. Examples: "
                    "'openlane2 --design-dir ./design --tag run1', "
                    "'openlane2 --last-run --flow Classic'"
                ),
            },
            "design_dir": {
                "type": "string",
                "description": "Path to the design directory containing config.json",
            },
            "flow": {
                "type": "string",
                "enum": ["Classic", "OpenInclusive"],
                "description": "OpenLane2 flow type (default: Classic)",
            },
            "pdk": {
                "type": "string",
                "description": "PDK to use (e.g., sky130A, gf180mcuD)",
            },
            "tag": {
                "type": "string",
                "description": "Tag/name for this run",
            },
        },
        "required": ["command"],
    }
    read_only = False
    category = "eda"
    requires = ["openlane2"]

    async def execute(self, params: Dict[str, Any], context: ToolContext) -> ToolResult:
        """Execute OpenLane2 flow."""
        command = params.get("command", "")
        design_dir = params.get("design_dir")
        flow = params.get("flow", "Classic")
        pdk = params.get("pdk")
        tag = params.get("tag")

        openlane_path = self._find_openlane()
        if not openlane_path:
            return ToolResult.fail(
                "OpenLane2 not found. Install: pip install openlane"
            )

        try:
            # Build command
            cmd_parts = [openlane_path]
            if design_dir:
                cmd_parts.extend(["--design-dir", design_dir])
            if flow:
                cmd_parts.extend(["--flow", flow])
            if pdk:
                cmd_parts.extend(["--pdk", pdk])
            if tag:
                cmd_parts.extend(["--tag", tag])

            # If a raw command string is provided, use it
            if command and not design_dir:
                import shlex
                cmd_parts = shlex.split(command)

            working_dir = context.working_dir or os.getcwd()

            proc = await asyncio.create_subprocess_exec(
                *cmd_parts,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                cwd=working_dir,
            )
            stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=600)

            stdout_str = stdout.decode("utf-8", errors="replace")
            stderr_str = stderr.decode("utf-8", errors="replace")

            if proc.returncode == 0:
                return ToolResult.ok(
                    output=stdout_str or "OpenLane2 flow completed successfully.",
                    metadata={"returncode": 0, "flow": flow},
                )
            else:
                return ToolResult.fail(
                    error=f"OpenLane2 exited with code {proc.returncode}",
                    output=stderr_str or stdout_str,
                )

        except asyncio.TimeoutError:
            return ToolResult.fail("OpenLane2 execution timed out (600s limit)")
        except Exception as e:
            return ToolResult.fail(f"OpenLane2 error: {str(e)}")

    def _find_openlane(self) -> str:
        import shutil
        path = shutil.which("openlane2") or shutil.which("openlane")
        return path or ""
