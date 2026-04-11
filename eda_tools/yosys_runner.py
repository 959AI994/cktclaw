"""
Yosys Runner — subprocess adapter for the Yosys Open SYnthesis Suite.

Typical invocations:
    /yosys -p "read_verilog test.v; stat"
    /yosys -p "synth -top m0; stat"

Yosys is usually invoked with ``-p "script"`` for inline commands, or
``-s script.ys`` for script files.
"""

import os
from typing import List

from .base_runner import BaseRunner


class YosysRunner(BaseRunner):
    """Runner specialised for the Yosys synthesis tool."""

    tool_name = "Yosys"
    executable = os.environ.get("YOSYS_PATH", "yosys")
    default_timeout = 180  # synthesis can be slow

    def build_command(self, args: str) -> List[str]:
        """
        Build the Yosys command.

        If the user already supplied flags (e.g. ``-p "..."``), pass them
        through verbatim.  Otherwise, wrap the bare script text with
        ``-p "<script>"`` for convenience.
        """
        import shlex

        args = args.strip()

        # If args already contain flags like -p, -s, -f, pass through
        if args.startswith("-"):
            return [self.executable] + shlex.split(args)

        # Otherwise treat the whole string as an inline Yosys script
        return [self.executable, "-p", args]
