"""
Bash Tool — shell command execution.
"""

import asyncio
import os
from typing import Any, Dict

from ..base import BaseTool, ToolContext, ToolResult


class BashTool(BaseTool):
    """Execute shell commands."""

    name = "bash"
    description = (
        "Execute a shell command and return its output. "
        "Use for system operations, file manipulation, "
        "running build tools, or any CLI interaction."
    )
    parameters = {
        "type": "object",
        "properties": {
            "command": {
                "type": "string",
                "description": "The shell command to execute",
            },
            "timeout": {
                "type": "integer",
                "description": "Timeout in seconds (default: 120)",
            },
            "working_dir": {
                "type": "string",
                "description": "Working directory for the command (default: session working dir)",
            },
        },
        "required": ["command"],
    }
    read_only = False
    category = "system"

    async def execute(self, params: Dict[str, Any], context: ToolContext) -> ToolResult:
        """Execute a shell command."""
        command = params.get("command", "")
        timeout = params.get("timeout", 120)
        working_dir = params.get("working_dir") or context.working_dir or os.getcwd()

        if not command.strip():
            return ToolResult.fail("Empty command")

        try:
            proc = await asyncio.create_subprocess_shell(
                command,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                cwd=working_dir,
            )
            stdout, stderr = await asyncio.wait_for(
                proc.communicate(), timeout=timeout
            )

            stdout_str = stdout.decode("utf-8", errors="replace")
            stderr_str = stderr.decode("utf-8", errors="replace")

            output = stdout_str
            if stderr_str:
                output += f"\n[stderr]\n{stderr_str}" if output else stderr_str

            if proc.returncode == 0:
                return ToolResult.ok(
                    output=output or "(no output)",
                    metadata={"returncode": 0},
                )
            else:
                return ToolResult.fail(
                    error=f"Command exited with code {proc.returncode}",
                    output=output,
                    metadata={"returncode": proc.returncode},
                )

        except asyncio.TimeoutError:
            return ToolResult.fail(f"Command timed out after {timeout}s")
        except Exception as e:
            return ToolResult.fail(f"Execution error: {str(e)}")
