"""
CktMem paths — resolve on-disk memory locations and validate containment.

Resolves per-project memory roots, honors env overrides, and performs basic
path safety checks before reads or writes.
"""

import os
import re
from pathlib import Path
from typing import Optional
import subprocess


def get_project_root() -> Optional[str]:
    """
    Return the Git repository root when available.

    Returns:
        Absolute path to ``git rev-parse --show-toplevel``, or ``os.getcwd()``
        when Git is unavailable.
    """
    try:
        result = subprocess.run(
            ["git", "rev-parse", "--show-toplevel"],
            capture_output=True,
            text=True,
            check=True,
        )
        return result.stdout.strip()
    except (subprocess.CalledProcessError, FileNotFoundError):
        return os.getcwd()


def sanitize_path(path: str) -> str:
    """
    Turn an arbitrary path string into a single filesystem-safe directory token.

    Args:
        path: Raw path fragment (often a project root).

    Returns:
        Sanitized token containing only ``[A-Za-z0-9_-]`` with stable underscores.
    """
    sanitized = re.sub(r'[^\w\-]', '_', path)
    sanitized = re.sub(r'_+', '_', sanitized)
    sanitized = sanitized.strip('_')
    return sanitized


def get_memory_base_dir() -> str:
    """
    Shared parent directory for all project-scoped memory folders.

    Returns:
        ``~/.cktclaw/projects`` (created if missing).
    """
    home = Path.home()
    base_dir = home / ".cktclaw" / "projects"
    base_dir.mkdir(parents=True, exist_ok=True)
    return str(base_dir)


def get_auto_mem_path(project_root: Optional[str] = None) -> str:
    """
    Absolute path to the auto-memory directory for a project.

    Args:
        project_root: Optional override; defaults to ``get_project_root()``.

    Returns:
        Path shaped like ``~/.cktclaw/projects/<sanitized_root>/memory/``.
    """
    override = os.environ.get("CKTCLAW_MEMORY_PATH_OVERRIDE")
    if override:
        path = Path(override)
        path.mkdir(parents=True, exist_ok=True)
        return str(path)

    if project_root is None:
        project_root = get_project_root()

    sanitized_project = sanitize_path(project_root or "default")

    memory_dir = Path(get_memory_base_dir()) / sanitized_project / "memory"
    memory_dir.mkdir(parents=True, exist_ok=True)

    return str(memory_dir)


def is_auto_memory_enabled() -> bool:
    """
    Return False when auto-memory should be skipped entirely.

    Honours ``CKTCLAW_DISABLE_AUTO_MEMORY`` and ``CKTCLAW_SIMPLE`` flags.
    """
    if os.environ.get("CKTCLAW_DISABLE_AUTO_MEMORY", "").lower() in ["1", "true", "yes"]:
        return False

    if os.environ.get("CKTCLAW_SIMPLE", "").lower() in ["1", "true", "yes"]:
        return False

    return True


def is_auto_mem_path(path: str, memory_root: Optional[str] = None) -> bool:
    """
    True when ``path`` resolves inside the configured memory root.

    Args:
        path: Candidate file or directory.
        memory_root: Optional explicit root; defaults to ``get_auto_mem_path()``.
    """
    if memory_root is None:
        memory_root = get_auto_mem_path()

    try:
        path_obj = Path(path).resolve()
        root_obj = Path(memory_root).resolve()
        return path_obj.is_relative_to(root_obj)
    except (ValueError, OSError):
        return False


ENTRYPOINT_NAME = "MEMORY.md"
MAX_ENTRYPOINT_LINES = 200
MAX_ENTRYPOINT_BYTES = 25_000


if __name__ == "__main__":
    print("CktMem paths smoke test")
    print("=" * 60)
    print(f"project_root={get_project_root()}")
    print(f"memory_base_dir={get_memory_base_dir()}")
    print(f"auto_mem_path={get_auto_mem_path()}")
    print(f"auto_memory_enabled={is_auto_memory_enabled()}")
    print(f"entrypoint={ENTRYPOINT_NAME}")
    print("=" * 60)
