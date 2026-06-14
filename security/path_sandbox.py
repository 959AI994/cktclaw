"""
Path Sandbox — restricts file system access to allowed roots.

Validates tool arguments containing paths against:
1. Allowed root directories (containment check after symlink resolution)
2. Denied glob patterns (e.g., **/.env, **/credentials*)
3. Dangerous command patterns (rm -rf /, curl|bash, etc.)
"""

import logging
import os
import re
from fnmatch import fnmatch
from pathlib import Path
from typing import List, Tuple

logger = logging.getLogger(__name__)

# Default denied patterns
DEFAULT_DENIED_PATTERNS = [
    "**/.env",
    "**/.env.*",
    "**/credentials*",
    "**/secrets*",
    "/etc/*",
    "/root/.ssh/*",
    "**/id_rsa*",
    "**/id_ed25519*",
    "**/.aws/credentials",
    "**/.git/config",
]

# Dangerous command patterns
DANGEROUS_COMMAND_PATTERNS = [
    r"rm\s+-rf\s+/",
    r"rm\s+-rf\s+\*",
    r"dd\s+if=/dev/zero",
    r"dd\s+if=/dev/random",
    r"mkfs\.",
    r"curl\s+.*\|\s*(ba)?sh",
    r"wget\s+.*\|\s*(ba)?sh",
    r"chmod\s+777\s+/",
    r"chown\s+-R\s+.*\s+/",
    r">\s*/dev/sd[a-z]",
    r":()\{\s*:\|:&\s*\};:",  # fork bomb
]

# EDA-specific dangerous patterns
EDA_DANGEROUS_PATTERNS = [
    r"write_verilog\s+/dev/",
    r"exec\s+",  # TCL exec command
    r"source\s+.*\.sh",  # sourcing shell scripts in TCL
    r"open\s+\|",  # TCL pipe to command
]


class PathSandbox:
    """
    Validates paths and commands against security policies.

    Args:
        allowed_roots: Directories where file access is permitted.
                      Empty list means no path restriction (permissive mode).
        denied_patterns: Glob patterns that are always blocked.
    """

    def __init__(
        self,
        allowed_roots: List[str] = None,
        denied_patterns: List[str] = None,
    ):
        self.allowed_roots = [
            Path(p).resolve() for p in (allowed_roots or [])
        ]
        self.denied_patterns = denied_patterns or DEFAULT_DENIED_PATTERNS
        self._dangerous_re = [
            re.compile(p, re.IGNORECASE) for p in DANGEROUS_COMMAND_PATTERNS
        ]
        self._eda_dangerous_re = [
            re.compile(p, re.IGNORECASE) for p in EDA_DANGEROUS_PATTERNS
        ]

    def validate_path(self, path: str) -> Tuple[bool, str]:
        """
        Check if a file path is allowed.

        Resolves symlinks, checks containment in allowed_roots,
        and checks denied_patterns.

        Args:
            path: The path to validate.

        Returns:
            (is_allowed, reason) — reason is empty if allowed.
        """
        if not path or not path.strip():
            return True, ""

        # Normalize the path
        try:
            resolved = Path(path).resolve()
        except (OSError, ValueError) as e:
            return False, f"Invalid path: {e}"

        # Check denied patterns against both original and resolved path
        path_str = str(resolved)
        original_path = path
        for pattern in self.denied_patterns:
            check_pattern = pattern.replace("**", "*")
            # Match against resolved full path
            if fnmatch(path_str, check_pattern):
                return False, f"Path matches denied pattern: {pattern}"
            # Match against original path (before symlink resolution)
            if fnmatch(original_path, check_pattern):
                return False, f"Path matches denied pattern: {pattern}"
            # Match against just the filename
            basename = os.path.basename(path_str)
            clean_pattern = check_pattern.lstrip("*/")
            if clean_pattern and fnmatch(basename, clean_pattern):
                return False, f"Path matches denied pattern: {pattern}"
            # Check if path starts with the denied prefix (both original and resolved)
            prefix = pattern.rstrip("*").rstrip("/")
            if prefix and (path_str.startswith(prefix) or original_path.startswith(prefix)):
                return False, f"Path matches denied pattern: {pattern}"

        # Path traversal detection
        if ".." in path:
            # Check if resolved path escapes after normalization
            normalized = os.path.normpath(path)
            if normalized.startswith("..") or "/../" in path:
                return False, "Path traversal detected"

        # Containment check (only if allowed_roots is configured)
        if self.allowed_roots:
            contained = any(
                self._is_contained(resolved, root)
                for root in self.allowed_roots
            )
            if not contained:
                return False, (
                    f"Path '{resolved}' is outside allowed roots: "
                    f"{[str(r) for r in self.allowed_roots]}"
                )

        return True, ""

    def validate_command(self, cmd: str) -> Tuple[bool, str]:
        """
        Check if a shell command is safe to execute.

        Detects dangerous patterns like rm -rf /, dd, curl|bash, etc.

        Args:
            cmd: The command string to validate.

        Returns:
            (is_allowed, reason) — reason is empty if allowed.
        """
        if not cmd or not cmd.strip():
            return True, ""

        # Check general dangerous patterns
        for pattern_re in self._dangerous_re:
            if pattern_re.search(cmd):
                return False, f"Dangerous command pattern detected: {pattern_re.pattern}"

        # Check EDA-specific dangerous patterns
        for pattern_re in self._eda_dangerous_re:
            if pattern_re.search(cmd):
                return False, f"Dangerous EDA command pattern: {pattern_re.pattern}"

        return True, ""

    def validate_tool_arguments(self, arguments: dict) -> Tuple[bool, str]:
        """
        Scan tool call arguments for path violations.

        Recursively checks string values that look like file paths.

        Args:
            arguments: Tool call argument dict.

        Returns:
            (is_allowed, reason) — reason is empty if allowed.
        """
        for key, value in arguments.items():
            if isinstance(value, str):
                # Check if value looks like a path
                if self._looks_like_path(value):
                    is_ok, reason = self.validate_path(value)
                    if not is_ok:
                        return False, f"Argument '{key}': {reason}"

                # Check if value looks like a command
                if self._looks_like_command(key, value):
                    is_ok, reason = self.validate_command(value)
                    if not is_ok:
                        return False, f"Argument '{key}': {reason}"

            elif isinstance(value, dict):
                is_ok, reason = self.validate_tool_arguments(value)
                if not is_ok:
                    return False, reason

            elif isinstance(value, list):
                for item in value:
                    if isinstance(item, str) and self._looks_like_path(item):
                        is_ok, reason = self.validate_path(item)
                        if not is_ok:
                            return False, reason

        return True, ""

    @staticmethod
    def _is_contained(path: Path, root: Path) -> bool:
        """Check if path is under root (after resolution)."""
        try:
            path.relative_to(root)
            return True
        except ValueError:
            return False

    @staticmethod
    def _looks_like_path(value: str) -> bool:
        """Heuristic: does the string look like a file path?"""
        if not value:
            return False
        # Starts with / or ./ or ../ or contains path separators
        if value.startswith(("/", "./", "../")):
            return True
        # Contains common file extensions with path separator
        if re.search(r"\.\w{1,5}$", value) and ("/" in value or "\\" in value):
            return True
        return False

    @staticmethod
    def _looks_like_command(key: str, value: str) -> bool:
        """Heuristic: does the argument look like a shell command?"""
        command_keys = {"cmd", "command", "script", "shell", "exec", "run"}
        if key.lower() in command_keys:
            return True
        # Contains pipe or semicolon (command chaining)
        if "|" in value or ";" in value:
            return True
        return False
