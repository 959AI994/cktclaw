"""
ABC Runner — subprocess adapter for the Berkeley ABC synthesis tool.

Typical invocations:
    /abc -c "read test.aig; print_stats"
    /abc -c "read_verilog test.v; strash; print_stats; quit"

ABC is usually invoked with ``-c "script"`` for non-interactive use.
"""

import os
import shutil
from pathlib import Path
from typing import List

from .base_runner import BaseRunner


def _is_readable_file(path: Path) -> bool:
    """Return True if path is a regular file; never raise on permission errors."""
    try:
        return path.is_file()
    except OSError:
        return False


def _find_abc_executable() -> str:
    """Resolve ABC path: ABC_PATH env > deps/oss-cad-suite > PATH lookup."""
    env = os.environ.get("ABC_PATH", "").strip()
    if env:
        return env
    pkg_root = Path(__file__).resolve().parent.parent
    deps_abc = pkg_root / "deps" / "oss-cad-suite" / "bin" / "yosys-abc"
    if _is_readable_file(deps_abc):
        return str(deps_abc)
    for candidate in ("abc", "yosys-abc"):
        found = shutil.which(candidate)
        if found:
            return found
    return "abc"


class ABCRunner(BaseRunner):
    """Runner specialised for the ABC logic synthesis tool."""

    tool_name = "ABC"
    executable = _find_abc_executable()
    default_timeout = 120

    def build_command(self, args: str) -> List[str]:
        """
        Build the ABC command.

        If the user already supplied flags (e.g. ``-c "..."``), pass them
        through verbatim.  Otherwise, wrap the bare script text with
        ``-c "<script>"`` so the user can type just the ABC commands.
        """
        import shlex

        args = args.strip()

        # If args already contain flags like -c, -f, -F, -s, pass through
        if args.startswith("-"):
            return [self.executable] + shlex.split(args)

        # Otherwise treat the whole string as an inline script
        return [self.executable, "-c", args]
