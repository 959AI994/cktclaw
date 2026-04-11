"""
EDA Tools Adapter Layer

Provides subprocess-based runners for external EDA tools (ABC, Yosys, etc.).
Each tool inherits from BaseRunner, which encapsulates:
- subprocess invocation with timeout
- stdout / stderr capture
- FileNotFoundError handling
"""

from .base_runner import BaseRunner, RunResult
from .abc_runner import ABCRunner
from .yosys_runner import YosysRunner

__all__ = [
    "BaseRunner",
    "RunResult",
    "ABCRunner",
    "YosysRunner",
]
