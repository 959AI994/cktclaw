"""
Magic VLSI Tool — layout DRC/LVS.
"""

import asyncio
import os
import tempfile
from typing import Any, Dict

from cktclaw.tools.base import BaseTool, ToolContext, ToolResult


class MagicTool(BaseTool):
    """Run Magic VLSI for layout operations, DRC, and LVS."""

    name = "magic"
    description = (
        "Run Magic VLSI layout tool. Supports DRC (design rule check), "
        "LVS (layout vs schematic), GDS reading/writing, and interactive "
        "layout editing via TCL scripting."
    )
    parameters = {
        "type": "object",
        "properties": {
            "command": {
                "type": "string",
                "description": (
                    "Magic TCL command to execute. Examples: "
                    "'gds read design.gds; drc check; drc count', "
                    "'load design; ext2spice'"
                ),
            },
            "gds_file": {
                "type": "string",
                "description": "Path to GDS file for DRC/LVS",
            },
            "operation": {
                "type": "string",
                "enum": ["drc", "lvs", "extract", "gds_read", "gds_write"],
                "description": "High-level operation to perform",
            },
            "tech_file": {
                "type": "string",
                "description": "Technology file for DRC rules",
            },
        },
        "required": ["command"],
    }
    read_only = False
    category = "eda"
    requires = ["magic"]

    async def execute(self, params: Dict[str, Any], context: ToolContext) -> ToolResult:
        """Execute Magic VLSI command."""
        command = params.get("command", "")

        magic_path = self._find_magic()
        if not magic_path:
            return ToolResult.fail(
                "Magic VLSI not found. Install: apt install magic"
            )

        try:
            # Write TCL script
            with tempfile.NamedTemporaryFile(
                mode="w", suffix=".tcl", delete=False
            ) as f:
                f.write(command)
                f.write("\nquit\n")
                tcl_path = f.name

            working_dir = context.working_dir or os.getcwd()

            proc = await asyncio.create_subprocess_exec(
                magic_path, "-dnull", "-noconsole", tcl_path,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                cwd=working_dir,
            )
            stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=120)

            os.unlink(tcl_path)

            stdout_str = stdout.decode("utf-8", errors="replace")
            stderr_str = stderr.decode("utf-8", errors="replace")

            if proc.returncode == 0:
                return ToolResult.ok(output=stdout_str or stderr_str)
            else:
                return ToolResult.fail(
                    error=f"Magic exited with code {proc.returncode}",
                    output=stderr_str or stdout_str,
                )

        except asyncio.TimeoutError:
            return ToolResult.fail("Magic execution timed out (120s limit)")
        except Exception as e:
            return ToolResult.fail(f"Magic error: {str(e)}")

    def _find_magic(self) -> str:
        import shutil
        return shutil.which("magic") or ""
