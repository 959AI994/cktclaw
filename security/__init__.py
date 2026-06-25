"""
CktClaw Security Layer — path sandboxing and threat detection.

Protects tool execution from:
- Path traversal attacks
- Dangerous command patterns
- Prompt injection in tool outputs
- EDA-specific exploit vectors
"""

from .path_sandbox import PathSandbox
from .threat_patterns import ThreatDetector, ThreatMatch

__all__ = [
    "PathSandbox",
    "ThreatDetector",
    "ThreatMatch",
]
