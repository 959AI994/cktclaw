"""
File Tools — read, write, and search files.
"""

import os
from pathlib import Path
from typing import Any, Dict

from ..base import BaseTool, ToolContext, ToolResult


class ReadFileTool(BaseTool):
    """Read file contents."""

    name = "read_file"
    description = "Read the contents of a file from the filesystem."
    parameters = {
        "type": "object",
        "properties": {
            "path": {
                "type": "string",
                "description": "Path to the file to read",
            },
            "offset": {
                "type": "integer",
                "description": "Line number to start reading from (0-indexed)",
            },
            "limit": {
                "type": "integer",
                "description": "Maximum number of lines to read",
            },
        },
        "required": ["path"],
    }
    read_only = True
    category = "system"

    async def execute(self, params: Dict[str, Any], context: ToolContext) -> ToolResult:
        """Read a file."""
        file_path = params.get("path", "")
        offset = params.get("offset", 0)
        limit = params.get("limit", 2000)

        if not file_path:
            return ToolResult.fail("No file path provided")

        # Resolve relative paths
        if not os.path.isabs(file_path):
            file_path = os.path.join(context.working_dir or os.getcwd(), file_path)

        if not os.path.isfile(file_path):
            return ToolResult.fail(f"File not found: {file_path}")

        try:
            with open(file_path, "r", errors="replace") as f:
                lines = f.readlines()

            total_lines = len(lines)
            selected = lines[offset:offset + limit]
            content = "".join(selected)

            return ToolResult.ok(
                output=content,
                metadata={
                    "total_lines": total_lines,
                    "lines_read": len(selected),
                    "offset": offset,
                },
            )
        except Exception as e:
            return ToolResult.fail(f"Error reading file: {str(e)}")


class WriteFileTool(BaseTool):
    """Write content to a file."""

    name = "write_file"
    description = "Write content to a file, creating it if it doesn't exist."
    parameters = {
        "type": "object",
        "properties": {
            "path": {
                "type": "string",
                "description": "Path to the file to write",
            },
            "content": {
                "type": "string",
                "description": "Content to write to the file",
            },
        },
        "required": ["path", "content"],
    }
    read_only = False
    category = "system"

    async def execute(self, params: Dict[str, Any], context: ToolContext) -> ToolResult:
        """Write to a file."""
        file_path = params.get("path", "")
        content = params.get("content", "")

        if not file_path:
            return ToolResult.fail("No file path provided")

        if not os.path.isabs(file_path):
            file_path = os.path.join(context.working_dir or os.getcwd(), file_path)

        try:
            os.makedirs(os.path.dirname(file_path), exist_ok=True)
            with open(file_path, "w") as f:
                f.write(content)
            return ToolResult.ok(
                output=f"Written {len(content)} bytes to {file_path}",
                artifacts=[file_path],
            )
        except Exception as e:
            return ToolResult.fail(f"Error writing file: {str(e)}")


class SearchFilesTool(BaseTool):
    """Search for files by pattern."""

    name = "search_files"
    description = "Search for files matching a glob pattern in the working directory."
    parameters = {
        "type": "object",
        "properties": {
            "pattern": {
                "type": "string",
                "description": "Glob pattern (e.g., '**/*.v', 'src/**/*.sv')",
            },
            "directory": {
                "type": "string",
                "description": "Directory to search in (default: working directory)",
            },
        },
        "required": ["pattern"],
    }
    read_only = True
    category = "system"

    async def execute(self, params: Dict[str, Any], context: ToolContext) -> ToolResult:
        """Search for files."""
        pattern = params.get("pattern", "")
        directory = params.get("directory") or context.working_dir or os.getcwd()

        if not pattern:
            return ToolResult.fail("No search pattern provided")

        try:
            search_dir = Path(directory)
            matches = sorted(str(p) for p in search_dir.glob(pattern))

            if not matches:
                return ToolResult.ok(output="No files found matching pattern.")

            output = "\n".join(matches[:100])
            if len(matches) > 100:
                output += f"\n... and {len(matches) - 100} more files"

            return ToolResult.ok(
                output=output,
                metadata={"count": len(matches)},
            )
        except Exception as e:
            return ToolResult.fail(f"Search error: {str(e)}")
