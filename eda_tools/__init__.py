"""
EDA Tools Adapter Layer

Provides subprocess-based runners for external EDA tools (ABC, Yosys, OpenSTA, etc.).
Each tool inherits from BaseRunner, which encapsulates:
- subprocess invocation with timeout
- stdout / stderr capture
- FileNotFoundError handling
"""

from .base_runner import BaseRunner, RunResult
from .abc_runner import ABCRunner
from .yosys_runner import YosysRunner
from .opensta_runner import OpenSTARunner
from .tool_detection import (
    ToolStatus,
    ToolManifest,
    detect_all_tools,
    write_tool_manifest,
    load_tool_manifest,
)

__all__ = [
    "BaseRunner",
    "RunResult",
    "ABCRunner",
    "YosysRunner",
    "OpenSTARunner",
    "ToolStatus",
    "ToolManifest",
    "detect_all_tools",
    "write_tool_manifest",
    "load_tool_manifest",
]
