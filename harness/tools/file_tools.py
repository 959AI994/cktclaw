"""
File Tools - File Operation Tools

Implements file tools.

Core features:
1. FileReadTool - File reading
2. FileWriteTool - File writing
3. FileEditTool - File editing
4. GlobTool - File search
5. GrepTool - Content search
"""

import os
from pathlib import Path
from typing import Optional, List, Dict, Any
from dataclasses import dataclass
import glob
import re


@dataclass
class FileReadResult:
    """File read result"""
    content: str
    line_count: int
    file_size: int
    encoding: str = "utf-8"


@dataclass
class FileWriteResult:
    """File write result"""
    success: bool
    bytes_written: int
    message: str


@dataclass
class FileEditResult:
    """File edit result"""
    success: bool
    lines_changed: int
    message: str


@dataclass
class GlobResult:
    """File search result"""
    files: List[str]
    count: int


@dataclass
class GrepResult:
    """Content search result"""
    matches: List[Dict[str, Any]]
    count: int


class FileReadTool:
    """File read tool"""

    @staticmethod
    def read(
        file_path: str,
        offset: int = 0,
        limit: Optional[int] = None,
        encoding: str = "utf-8"
    ) -> FileReadResult:
        """
        Read file

        Args:
            file_path: File path
            offset: Starting line number
            limit: Line read limit
            encoding: File encoding

        Returns:
            File read result
        """
        path = Path(file_path).expanduser().resolve()

        if not path.exists():
            raise FileNotFoundError(f"File not found: {file_path}")

        if not path.is_file():
            raise ValueError(f"Not a file: {file_path}")

        # Read file
        with open(path, 'r', encoding=encoding) as f:
            lines = f.readlines()

        # Apply offset and limit
        if offset > 0:
            lines = lines[offset:]

        if limit is not None:
            lines = lines[:limit]

        content = "".join(lines)
        file_size = path.stat().st_size

        return FileReadResult(
            content=content,
            line_count=len(lines),
            file_size=file_size,
            encoding=encoding
        )


class FileWriteTool:
    """File write tool"""

    @staticmethod
    def write(
        file_path: str,
        content: str,
        encoding: str = "utf-8",
        create_dirs: bool = True
    ) -> FileWriteResult:
        """
        Write file

        Args:
            file_path: File path
            content: File content
            encoding: File encoding
            create_dirs: Whether to create directories

        Returns:
            File write result
        """
        path = Path(file_path).expanduser().resolve()

        # Create directories
        if create_dirs:
            path.parent.mkdir(parents=True, exist_ok=True)

        # Write file
        with open(path, 'w', encoding=encoding) as f:
            bytes_written = f.write(content)

        return FileWriteResult(
            success=True,
            bytes_written=bytes_written,
            message=f"Successfully wrote {bytes_written} bytes to {file_path}"
        )


class FileEditTool:
    """File edit tool"""

    @staticmethod
    def edit(
        file_path: str,
        old_string: str,
        new_string: str,
        replace_all: bool = False
    ) -> FileEditResult:
        """
        Edit file (string replacement)

        Args:
            file_path: File path
            old_string: String to replace
            new_string: New string
            replace_all: Whether to replace all matches

        Returns:
            File edit result
        """
        path = Path(file_path).expanduser().resolve()

        if not path.exists():
            raise FileNotFoundError(f"File not found: {file_path}")

        # Read file
        with open(path, 'r', encoding='utf-8') as f:
            content = f.read()

        # Replace
        if replace_all:
            new_content = content.replace(old_string, new_string)
            count = content.count(old_string)
        else:
            # Only replace first match
            new_content = content.replace(old_string, new_string, 1)
            count = 1 if old_string in content else 0

        if count == 0:
            return FileEditResult(
                success=False,
                lines_changed=0,
                message=f"String not found: {old_string[:50]}..."
            )

        # Write back to file
        with open(path, 'w', encoding='utf-8') as f:
            f.write(new_content)

        return FileEditResult(
            success=True,
            lines_changed=count,
            message=f"Successfully replaced {count} occurrence(s)"
        )


class GlobTool:
    """File search tool"""

    @staticmethod
    def glob(
        pattern: str,
        path: Optional[str] = None,
        recursive: bool = True
    ) -> GlobResult:
        """
        Search files

        Args:
            pattern: Glob pattern
            path: Search path
            recursive: Whether to search recursively

        Returns:
            File search result
        """
        if path is None:
            path = os.getcwd()

        search_path = Path(path).expanduser().resolve()

        if not search_path.exists():
            raise FileNotFoundError(f"Path not found: {path}")

        # Execute search
        if recursive:
            full_pattern = str(search_path / "**" / pattern)
            files = glob.glob(full_pattern, recursive=True)
        else:
            full_pattern = str(search_path / pattern)
            files = glob.glob(full_pattern, recursive=False)

        # Filter out directories
        files = [f for f in files if os.path.isfile(f)]

        # Sort
        files.sort()

        return GlobResult(
            files=files,
            count=len(files)
        )


class GrepTool:
    """Content search tool"""

    @staticmethod
    def grep(
        pattern: str,
        path: Optional[str] = None,
        file_pattern: Optional[str] = None,
        case_sensitive: bool = True,
        max_results: int = 100
    ) -> GrepResult:
        """
        Search file content

        Args:
            pattern: Search pattern (regular expression)
            path: Search path
            file_pattern: File pattern
            case_sensitive: Whether case sensitive
            max_results: Maximum result count

        Returns:
            Content search result
        """
        if path is None:
            path = os.getcwd()

        search_path = Path(path).expanduser().resolve()

        if not search_path.exists():
            raise FileNotFoundError(f"Path not found: {path}")

        # Compile regular expression
        flags = 0 if case_sensitive else re.IGNORECASE
        regex = re.compile(pattern, flags)

        # Get files to search
        if file_pattern:
            glob_result = GlobTool.glob(file_pattern, str(search_path))
            files = glob_result.files
        else:
            # Search all text files
            glob_result = GlobTool.glob("*", str(search_path))
            files = glob_result.files

        # Search content
        matches = []

        for file_path in files:
            if len(matches) >= max_results:
                break

            try:
                with open(file_path, 'r', encoding='utf-8', errors='ignore') as f:
                    for line_num, line in enumerate(f, 1):
                        if len(matches) >= max_results:
                            break

                        if regex.search(line):
                            matches.append({
                                "file": file_path,
                                "line": line_num,
                                "content": line.rstrip(),
                            })
            except Exception:
                # Skip files that cannot be read
                continue

        return GrepResult(
            matches=matches,
            count=len(matches)
        )


# Tool registration
FILE_TOOLS = {
    "Read": FileReadTool,
    "Write": FileWriteTool,
    "Edit": FileEditTool,
    "Glob": GlobTool,
    "Grep": GrepTool,
}
