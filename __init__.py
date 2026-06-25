"""
CktClaw: The Autonomous Multi-Agent Ecosystem for Intelligent EDA

A modern REPL interface for AIG-to-Verilog conversion and circuit analysis.

v2.1 modules:
- security: Path sandboxing + threat detection
- tools.repair: Tool call argument repair
- cktmem.llm_compactor: LLM-backed context summarization
- config_loader: YAML configuration
- trajectory: Structured audit logging

v3.0 modules:
- loop: Cross-domain system closed loop (EDA + Chip + AI Infra)
"""

import sys
from pathlib import Path

# Add project root to path for webapp imports
_PROJECT_ROOT = Path(__file__).parent.parent.resolve()
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

__version__ = "3.0.0"
__author__ = "Jingxin Wang"

__all__ = [
    "main",
    "LogicRTCLI",
    "CLIState",
    "parse_input",
]


def __getattr__(name: str):
    """Lazy-import from .main to avoid RuntimeWarning with ``python -m cktclaw.main``."""
    if name in ("main", "LogicRTCLI", "CLIState", "parse_input"):
        from . import main as _main_mod
        return getattr(_main_mod, name)
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")


# Entry point for console_scripts
if __name__ == "__main__":
    from .main import main
    main()
