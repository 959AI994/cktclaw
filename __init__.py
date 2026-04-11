"""
CktClaw: The Autonomous Multi-Agent Ecosystem for Intelligent EDA

A modern REPL interface for AIG-to-Verilog conversion and circuit analysis.
"""

import sys
from pathlib import Path

# Add project root to path for webapp imports
_PROJECT_ROOT = Path(__file__).parent.parent.resolve()
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

from .main import main, LogicRTCLI, CLIState, parse_input

__version__ = "1.0.0"
__author__ = "Jingxin Wang"

__all__ = [
    "main",
    "LogicRTCLI",
    "CLIState",
    "parse_input",
]

# Entry point for console_scripts
if __name__ == "__main__":
    main()
