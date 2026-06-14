"""
Tool Guardrails — prevents infinite loops, enforces output limits, tracks call history.

Production safety layer for tool execution:
1. Detects repeated identical tool calls (blocks after N duplicates)
2. Truncates tool output to configurable max size
3. Enforces per-turn tool call budget
"""

import hashlib
import json
import logging
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

# Defaults
DEFAULT_MAX_DUPLICATES = 3
DEFAULT_MAX_OUTPUT_CHARS = 8000
DEFAULT_PER_TURN_LIMIT = 30


@dataclass
class ToolCallRecord:
    """Record of a single tool call for deduplication."""
    name: str
    args_hash: str
    count: int = 1


@dataclass
class GuardrailViolation:
    """Describes why a tool call was blocked."""
    reason: str
    tool_name: str
    details: str = ""

    def __str__(self) -> str:
        return f"[Guardrail] {self.reason}: {self.tool_name} — {self.details}"


class ToolGuardrails:
    """
    Tracks tool call history within a turn and enforces safety limits.

    Usage:
        guardrails = ToolGuardrails()
        # Before each tool call:
        violation = guardrails.check(tool_name, tool_args)
        if violation:
            # Block the call, return violation message to LLM
            ...
        # After execution:
        output = guardrails.truncate_output(raw_output)
    """

    def __init__(
        self,
        max_duplicates: int = DEFAULT_MAX_DUPLICATES,
        max_output_chars: int = DEFAULT_MAX_OUTPUT_CHARS,
        per_turn_limit: int = DEFAULT_PER_TURN_LIMIT,
    ):
        self.max_duplicates = max_duplicates
        self.max_output_chars = max_output_chars
        self.per_turn_limit = per_turn_limit

        # State
        self._call_history: Dict[str, ToolCallRecord] = {}  # hash -> record
        self._total_calls: int = 0

    def check(
        self, tool_name: str, tool_args: Dict[str, Any]
    ) -> Optional[GuardrailViolation]:
        """
        Check if a tool call should be allowed.

        Args:
            tool_name: Name of the tool being called.
            tool_args: Arguments to the tool.

        Returns:
            GuardrailViolation if blocked, None if allowed.
        """
        # Check per-turn limit
        if self._total_calls >= self.per_turn_limit:
            return GuardrailViolation(
                reason="per_turn_limit_exceeded",
                tool_name=tool_name,
                details=f"Exceeded {self.per_turn_limit} tool calls this turn. "
                        f"Stop calling tools and summarize results.",
            )

        # Check for duplicate calls
        call_hash = self._hash_call(tool_name, tool_args)
        record = self._call_history.get(call_hash)

        if record and record.count >= self.max_duplicates:
            return GuardrailViolation(
                reason="repeated_identical_call",
                tool_name=tool_name,
                details=f"Tool '{tool_name}' called {record.count} times with "
                        f"identical arguments. Blocked to prevent infinite loop. "
                        f"Try a different approach or arguments.",
            )

        # Record the call
        if record:
            record.count += 1
        else:
            self._call_history[call_hash] = ToolCallRecord(
                name=tool_name, args_hash=call_hash
            )

        self._total_calls += 1
        return None

    def truncate_output(self, output: str, tool_name: str = "") -> str:
        """
        Truncate tool output if it exceeds max size.

        Args:
            output: Raw tool output string.
            tool_name: Optional tool name for logging.

        Returns:
            Truncated output with indicator if truncation occurred.
        """
        if len(output) <= self.max_output_chars:
            return output

        truncated = output[: self.max_output_chars]
        suffix = (
            f"\n\n[OUTPUT TRUNCATED: {len(output)} chars total, "
            f"showing first {self.max_output_chars}. "
            f"Use more specific queries to get relevant portions.]"
        )
        logger.info(
            f"Truncated output from tool '{tool_name}': "
            f"{len(output)} -> {self.max_output_chars} chars"
        )
        return truncated + suffix

    def reset(self) -> None:
        """Reset all state (call at start of each conversation turn)."""
        self._call_history.clear()
        self._total_calls = 0

    @property
    def total_calls(self) -> int:
        """Total tool calls made this turn."""
        return self._total_calls

    @property
    def call_summary(self) -> List[Dict[str, Any]]:
        """Summary of all calls made (for trajectory logging)."""
        return [
            {"name": r.name, "count": r.count}
            for r in self._call_history.values()
        ]

    @staticmethod
    def _hash_call(tool_name: str, tool_args: Dict[str, Any]) -> str:
        """Create a stable hash of tool name + arguments."""
        payload = json.dumps(
            {"name": tool_name, "args": tool_args},
            sort_keys=True,
            default=str,
        )
        return hashlib.sha256(payload.encode()).hexdigest()[:16]
