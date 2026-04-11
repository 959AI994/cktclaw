"""
OpenSTA Runner — subprocess adapter for the OpenSTA static timing analysis tool.

Typical invocations:
    /opensta -c "read_liberty lib.lib; read_verilog design.v; report_checks"
    /opensta script.tcl

OpenSTA uses Tcl scripting. Commands can be passed via:
- Direct script file: sta script.tcl
- Inline commands: sta -c "command1; command2"
"""

import os
from typing import List

from .base_runner import BaseRunner


class OpenSTARunner(BaseRunner):
    """Runner specialised for the OpenSTA timing analysis tool."""

    tool_name = "OpenSTA"
    executable = os.environ.get("OPENSTA_PATH", "sta")
    default_timeout = 180  # timing analysis can be slow

    def build_command(self, args: str) -> List[str]:
        """
        Build the OpenSTA command.

        If the user already supplied flags (e.g. ``-c "..."``), pass them
        through verbatim. Otherwise, wrap the bare script text with
        ``-c "<script>"`` for convenience.
        """
        import shlex

        args = args.strip()

        # If args already contain flags like -c, -f, -threads, pass through
        if args.startswith("-"):
            return [self.executable] + shlex.split(args)

        # If args look like a file path (ends with .tcl or contains /), pass directly
        if args.endswith(".tcl") or "/" in args or "\\" in args:
            return [self.executable, args]

        # Otherwise treat the whole string as an inline Tcl script
        return [self.executable, "-c", args]
