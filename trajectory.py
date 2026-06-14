"""
Trajectory Logger — structured audit trail of agent decisions.

Logs every LLM call, tool call, and result to a JSONL file per session.
Provides full observability for debugging and analysis.
"""

import json
import logging
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Optional

logger = logging.getLogger(__name__)

# Default trajectory directory
DEFAULT_TRAJECTORY_DIR = Path(".cktclaw") / "trajectories"


class TrajectoryLogger:
    """
    Logs agent interactions to structured JSONL files.

    Each session gets its own file at:
        .cktclaw/trajectories/<session_id>.jsonl

    Each line is a JSON object with:
        - timestamp: ISO 8601
        - event_type: user_message | assistant_message | tool_call | tool_result | error
        - session_id: Session identifier
        - data: Event-specific payload
    """

    def __init__(self, base_dir: Optional[Path] = None):
        self.base_dir = base_dir or DEFAULT_TRAJECTORY_DIR
        self._ensure_dir()

    def _ensure_dir(self) -> None:
        """Create trajectory directory if it doesn't exist."""
        try:
            self.base_dir.mkdir(parents=True, exist_ok=True)
        except OSError as e:
            logger.warning(f"Cannot create trajectory dir {self.base_dir}: {e}")

    def _get_file(self, session_id: str) -> Path:
        """Get the trajectory file path for a session."""
        safe_id = session_id.replace("/", "_").replace("..", "_")
        return self.base_dir / f"{safe_id}.jsonl"

    def _write_event(
        self,
        session_id: str,
        event_type: str,
        data: Dict[str, Any],
    ) -> None:
        """Write a single event to the session's trajectory file."""
        event = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "event_type": event_type,
            "session_id": session_id,
            "data": data,
        }
        try:
            filepath = self._get_file(session_id)
            with open(filepath, "a", encoding="utf-8") as f:
                f.write(json.dumps(event, ensure_ascii=False, default=str) + "\n")
        except OSError as e:
            logger.debug(f"Failed to write trajectory: {e}")

    def log_user_message(
        self,
        session_id: str,
        content: str,
    ) -> None:
        """Log a user message."""
        self._write_event(session_id, "user_message", {
            "content": content[:2000],
        })

    def log_assistant_message(
        self,
        session_id: str,
        content: str,
        provider: str = "",
        elapsed: float = 0.0,
    ) -> None:
        """Log an assistant response."""
        self._write_event(session_id, "assistant_message", {
            "content": content[:2000],
            "provider": provider,
            "elapsed_seconds": round(elapsed, 3),
        })

    def log_tool_call(
        self,
        session_id: str,
        tool_name: str,
        arguments: Dict[str, Any],
    ) -> None:
        """Log a tool call initiated by the LLM."""
        # Truncate large arguments for storage
        args_str = json.dumps(arguments, default=str)
        if len(args_str) > 1000:
            args_str = args_str[:1000] + "...(truncated)"

        self._write_event(session_id, "tool_call", {
            "tool_name": tool_name,
            "arguments": arguments if len(args_str) <= 1000 else {"_truncated": args_str},
        })

    def log_tool_result(
        self,
        session_id: str,
        tool_name: str,
        result: str,
        success: bool = True,
    ) -> None:
        """Log the result of a tool execution."""
        self._write_event(session_id, "tool_result", {
            "tool_name": tool_name,
            "result_preview": result[:500],
            "result_length": len(result),
            "success": success,
        })

    def log_error(
        self,
        session_id: str,
        error: str,
        category: str = "unknown",
    ) -> None:
        """Log an error event."""
        self._write_event(session_id, "error", {
            "error": error[:1000],
            "category": category,
        })

    def log_failover(
        self,
        session_id: str,
        from_provider: str,
        to_provider: str,
        reason: str = "",
    ) -> None:
        """Log a provider failover event."""
        self._write_event(session_id, "failover", {
            "from": from_provider,
            "to": to_provider,
            "reason": reason[:500],
        })

    def get_session_events(self, session_id: str) -> list:
        """Read all events for a session (for debugging/inspection)."""
        filepath = self._get_file(session_id)
        if not filepath.exists():
            return []

        events = []
        try:
            with open(filepath, "r", encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if line:
                        events.append(json.loads(line))
        except (OSError, json.JSONDecodeError) as e:
            logger.warning(f"Failed to read trajectory for {session_id}: {e}")

        return events


# Global singleton
_trajectory_logger: Optional[TrajectoryLogger] = None


def get_trajectory_logger(base_dir: Optional[Path] = None) -> TrajectoryLogger:
    """Get or create the global TrajectoryLogger."""
    global _trajectory_logger
    if _trajectory_logger is None:
        _trajectory_logger = TrajectoryLogger(base_dir=base_dir)
    return _trajectory_logger
