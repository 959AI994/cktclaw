"""
Threat Detection — scans tool outputs for injection attempts and malicious content.

Detects:
1. Prompt injection patterns ("ignore previous instructions", "system: you are now")
2. Command injection ($(...), `...`, ; rm, | curl)
3. Path traversal (../../etc/passwd)
4. EDA-specific threats (source .sh inside TCL, exec commands)
"""

import logging
import re
from dataclasses import dataclass
from typing import List

logger = logging.getLogger(__name__)


@dataclass
class ThreatMatch:
    """A detected threat in tool output."""
    category: str       # prompt_injection | command_injection | path_traversal | eda_exploit
    pattern: str        # The pattern that matched
    matched_text: str   # The actual text that triggered the match
    severity: str       # low | medium | high | critical
    position: int       # Character offset in the output

    def __str__(self) -> str:
        return f"[{self.severity.upper()}] {self.category}: '{self.matched_text[:80]}'"


# Prompt injection patterns
PROMPT_INJECTION_PATTERNS = [
    (r"ignore\s+(all\s+)?previous\s+instructions", "high"),
    (r"ignore\s+(all\s+)?prior\s+(instructions|context)", "high"),
    (r"system:\s*you\s+are\s+now", "critical"),
    (r"you\s+are\s+now\s+a\s+", "medium"),
    (r"forget\s+(everything|all)\s+(you|that)", "high"),
    (r"new\s+instructions?:\s*", "medium"),
    (r"override\s+(previous|prior|system)", "high"),
    (r"<\s*system\s*>", "high"),
    (r"\[SYSTEM\]\s*", "medium"),
    (r"IMPORTANT:\s*disregard", "high"),
    (r"act\s+as\s+if\s+(you\s+are|you're)\s+a", "medium"),
    (r"pretend\s+(you\s+are|you're|to\s+be)", "low"),
]

# Command injection patterns
COMMAND_INJECTION_PATTERNS = [
    (r"\$\([^)]+\)", "high"),              # $(command)
    (r"`[^`]+`", "medium"),                 # `command`
    (r";\s*rm\s+", "critical"),             # ; rm
    (r"\|\s*curl\s+", "high"),              # | curl
    (r"\|\s*wget\s+", "high"),              # | wget
    (r"\|\s*(ba)?sh", "critical"),          # | bash / | sh
    (r"&&\s*curl\s+", "high"),              # && curl
    (r"\|\s*nc\s+", "high"),               # | nc (netcat)
    (r";\s*python\s+-c", "high"),           # ; python -c
    (r";\s*perl\s+-e", "high"),             # ; perl -e
    (r"eval\s*\(", "high"),                 # eval(
]

# Path traversal patterns
PATH_TRAVERSAL_PATTERNS = [
    (r"\.\./\.\./.*etc/passwd", "critical"),
    (r"\.\./\.\./.*etc/shadow", "critical"),
    (r"\.\./\.\./\.\./", "high"),
    (r"%2e%2e[/\\]", "high"),              # URL-encoded ../
    (r"\.\.%2f", "high"),                   # Mixed encoding
    (r"/proc/self/", "medium"),
    (r"/dev/tcp/", "high"),
]

# EDA-specific exploit patterns
EDA_EXPLOIT_PATTERNS = [
    (r"source\s+[\"']?[^\"'\s]*\.sh", "medium"),  # source .sh in TCL
    (r"exec\s+[a-z]+", "medium"),                   # TCL exec
    (r"open\s+\|", "high"),                         # TCL pipe open
    (r"package\s+require\s+Tcl", "low"),            # TCL package load (info)
    (r"file\s+delete\s+-force", "high"),            # TCL file delete
]


class ThreatDetector:
    """
    Scans tool outputs for security threats.

    Used post-execution to detect injection attempts,
    malicious commands, and exploit patterns in results.
    """

    def __init__(self):
        self._compiled_patterns = {
            "prompt_injection": [
                (re.compile(p, re.IGNORECASE), sev)
                for p, sev in PROMPT_INJECTION_PATTERNS
            ],
            "command_injection": [
                (re.compile(p, re.IGNORECASE), sev)
                for p, sev in COMMAND_INJECTION_PATTERNS
            ],
            "path_traversal": [
                (re.compile(p, re.IGNORECASE), sev)
                for p, sev in PATH_TRAVERSAL_PATTERNS
            ],
            "eda_exploit": [
                (re.compile(p, re.IGNORECASE), sev)
                for p, sev in EDA_EXPLOIT_PATTERNS
            ],
        }

    def detect_in_tool_output(self, output: str) -> List[ThreatMatch]:
        """
        Scan tool output for threat patterns.

        Args:
            output: Raw tool output string.

        Returns:
            List of detected threats (may be empty).
        """
        if not output:
            return []

        threats = []

        for category, patterns in self._compiled_patterns.items():
            for pattern_re, severity in patterns:
                for match in pattern_re.finditer(output):
                    threats.append(ThreatMatch(
                        category=category,
                        pattern=pattern_re.pattern,
                        matched_text=match.group(0),
                        severity=severity,
                        position=match.start(),
                    ))

        return threats

    def sanitize_output(self, output: str) -> str:
        """
        Strip detected injection patterns while preserving legitimate content.

        Only removes high/critical severity matches to avoid false positives.

        Args:
            output: Raw tool output.

        Returns:
            Sanitized output with injections removed.
        """
        if not output:
            return output

        sanitized = output

        # Only sanitize prompt injection patterns (high+ severity)
        for pattern_re, severity in self._compiled_patterns["prompt_injection"]:
            if severity in ("high", "critical"):
                sanitized = pattern_re.sub("[REDACTED]", sanitized)

        return sanitized

    def get_threat_summary(self, threats: List[ThreatMatch]) -> str:
        """Format threats into a human-readable summary."""
        if not threats:
            return ""

        by_severity = {"critical": [], "high": [], "medium": [], "low": []}
        for t in threats:
            by_severity[t.severity].append(t)

        lines = ["Security threats detected in tool output:"]
        for sev in ("critical", "high", "medium", "low"):
            if by_severity[sev]:
                lines.append(f"  [{sev.upper()}] x{len(by_severity[sev])}:")
                for t in by_severity[sev][:3]:  # Cap at 3 per severity
                    lines.append(f"    - {t.category}: {t.matched_text[:60]}")

        return "\n".join(lines)
