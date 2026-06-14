"""
ABC Tool — logic optimization via ABC (Berkeley).

Wraps the existing abc_runner.py with the BaseTool interface.
"""

import asyncio
import os
import tempfile
from typing import Any, Dict

from ..base import BaseTool, ToolContext, ToolResult


class ABCTool(BaseTool):
    """Logic optimization using ABC (Berkeley)."""

    name = "abc"
    description = (
        "Run ABC logic synthesis and optimization. "
        "Supports AIG manipulation, technology mapping, "
        "sequential optimization, and equivalence checking. "
        "Input: BLIF, AIG, or Verilog (via read)."
    )
    parameters = {
        "type": "object",
        "properties": {
            "command": {
                "type": "string",
                "description": (
                    "ABC command sequence (semicolon-separated). Examples: "
                    "'read design.blif; resyn2; map; print_stats', "
                    "'read design.aig; dc2; dch; if -K 6; print_stats'"
                ),
            },
            "input_file": {
                "type": "string",
                "description": "Path to input file (AIG, BLIF, or Verilog)",
            },
            "optimization_script": {
                "type": "string",
                "enum": ["resyn", "resyn2", "resyn3", "compress", "compress2", "dc2"],
                "description": "Pre-defined optimization recipe to apply",
            },
        },
        "required": ["command"],
    }
    read_only = False
    category = "eda"
    requires = ["abc"]

    async def execute(self, params: Dict[str, Any], context: ToolContext) -> ToolResult:
        """Execute ABC optimization command."""
        command = params.get("command", "")
        input_file = params.get("input_file")

        abc_path = self._find_abc()
        if not abc_path:
            return ToolResult.fail("ABC not found. Set ABC_PATH environment variable.")

        try:
            # Build command string
            full_cmd = ""
            if input_file:
                full_cmd = f"read {input_file}; "
            full_cmd += command

            working_dir = context.working_dir or os.getcwd()

            proc = await asyncio.create_subprocess_exec(
                abc_path, "-c", full_cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                cwd=working_dir,
            )
            stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=120)

            stdout_str = stdout.decode("utf-8", errors="replace")
            stderr_str = stderr.decode("utf-8", errors="replace")

            if proc.returncode == 0:
                return ToolResult.ok(
                    output=stdout_str,
                    metadata={"returncode": 0},
                )
            else:
                return ToolResult.fail(
                    error=f"ABC exited with code {proc.returncode}",
                    output=stderr_str or stdout_str,
                )

        except asyncio.TimeoutError:
            return ToolResult.fail("ABC execution timed out (120s limit)")
        except Exception as e:
            return ToolResult.fail(f"ABC execution error: {str(e)}")

    def _find_abc(self) -> str:
        """Find the ABC binary."""
        import shutil
        env_path = os.environ.get("ABC_PATH", "")
        if env_path and os.path.isfile(env_path):
            return env_path
        path = shutil.which("abc")
        if path:
            return path
        return ""
