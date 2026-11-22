"""Structured progress events for chip automation runs.

This module is intentionally separate from ``runtime.audit``. Audit remains a
security trail; chip progress is a user-facing timeline that can be replayed in
the web dashboard and rendered in the CLI.
"""

from __future__ import annotations

import json
import re
from collections import deque
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Deque, Dict, List, Optional

from .run_context import get_current_run, run_dir_for

_SECRET_KEY = re.compile(r"(authorization|api[_-]?key|token|secret|bearer|password)", re.IGNORECASE)
_SECRET_VALUE = re.compile(r"(Bearer\s+\S+|sk-[A-Za-z0-9_\-]{8,})", re.IGNORECASE)

_EVENTS: Deque[Dict[str, Any]] = deque(maxlen=2000)


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def redact(obj: Any) -> Any:
    if isinstance(obj, dict):
        return {
            k: "[REDACTED]" if isinstance(k, str) and _SECRET_KEY.search(k) else redact(v)
            for k, v in obj.items()
        }
    if isinstance(obj, list):
        return [redact(v) for v in obj]
    if isinstance(obj, tuple):
        return [redact(v) for v in obj]
    if isinstance(obj, str):
        return _SECRET_VALUE.sub("[REDACTED]", obj)
    return obj


@dataclass
class ChipProgressEvent:
    run_id: str
    event_type: str
    mission_id: str = ""
    phase: str = ""
    agent: str = ""
    skill: str = ""
    tool: str = ""
    status: str = ""
    index: int = 0
    total: int = 0
    message: str = ""
    artifacts: List[str] = field(default_factory=list)
    qor: Dict[str, Any] = field(default_factory=dict)
    coverage: Dict[str, Any] = field(default_factory=dict)
    fix_request: Optional[Dict[str, Any]] = None
    metadata: Dict[str, Any] = field(default_factory=dict)
    timestamp: str = field(default_factory=_utc_now_iso)

    def to_dict(self) -> Dict[str, Any]:
        data = asdict(self)
        return redact(data)


def progress_run_id(cli_state: Any = None, run_id: str = "") -> str:
    """Resolve the externally visible run id for progress events."""
    if run_id:
        return run_id
    console = getattr(cli_state, "console", None) if cli_state is not None else None
    console_run_id = getattr(console, "run_id", "")
    if console_run_id:
        return str(console_run_id)
    state_run_id = getattr(cli_state, "run_id", "") if cli_state is not None else ""
    if state_run_id:
        return str(state_run_id)
    run = get_current_run()
    if run is not None:
        return run.run_id
    return ""


def progress_path_for(run_id: str = "") -> Optional[Path]:
    run = get_current_run()
    if run is not None:
        return run.dir / "progress.jsonl"
    if run_id:
        return run_dir_for(run_id) / "progress.jsonl"
    return None


def publish_chip_progress(
    *,
    event_type: str,
    cli_state: Any = None,
    run_id: str = "",
    mission_id: str = "",
    phase: str = "",
    agent: str = "",
    skill: str = "",
    tool: str = "",
    status: str = "",
    index: int = 0,
    total: int = 0,
    message: str = "",
    artifacts: Optional[List[str]] = None,
    qor: Optional[Dict[str, Any]] = None,
    coverage: Optional[Dict[str, Any]] = None,
    fix_request: Optional[Dict[str, Any]] = None,
    metadata: Optional[Dict[str, Any]] = None,
    quiet: bool = False,
    json_progress: bool = False,
) -> Dict[str, Any]:
    """Publish one chip progress event.

    Best-effort by design: event publication should never break a chip run.
    """
    resolved_run_id = progress_run_id(cli_state, run_id)
    event = ChipProgressEvent(
        run_id=resolved_run_id,
        mission_id=mission_id,
        event_type=event_type,
        phase=phase,
        agent=agent,
        skill=skill,
        tool=tool,
        status=status,
        index=index,
        total=total,
        message=message,
        artifacts=artifacts or [],
        qor=qor or {},
        coverage=coverage or {},
        fix_request=fix_request,
        metadata=metadata or {},
    )
    data = event.to_dict()
    _EVENTS.append(data)
    _append_progress_jsonl(data)
    _emit_web_event(data)
    _emit_cli_event(data, cli_state=cli_state, quiet=quiet, json_progress=json_progress)
    return data


def recent_chip_progress(run_id: str = "", limit: int = 200) -> List[Dict[str, Any]]:
    events = list(_EVENTS)
    if run_id:
        events = [e for e in events if e.get("run_id") == run_id]
    return events[-limit:]


def read_chip_progress(run_id: str, limit: int = 500) -> List[Dict[str, Any]]:
    path = run_dir_for(run_id) / "progress.jsonl"
    events: List[Dict[str, Any]] = []
    try:
        for line in path.read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            item = json.loads(line)
            if isinstance(item, dict):
                events.append(item)
    except Exception:
        events = []
    if not events:
        events = recent_chip_progress(run_id, limit=limit)
    return events[-limit:]


class ChipProgressConsoleSink:
    """Compact CLI renderer for chip automation progress."""

    def __init__(self, console: Any, *, json_progress: bool = False) -> None:
        self.console = console
        self.json_progress = json_progress

    def emit(self, event: Dict[str, Any]) -> None:
        if self.json_progress:
            self.console.print(json.dumps(event, ensure_ascii=False))
            return
        label = event.get("phase") or event.get("skill") or event.get("tool") or event.get("event_type")
        who = event.get("agent") or event.get("skill") or "chip"
        status = event.get("status") or event.get("event_type")
        idx = ""
        if event.get("index") and event.get("total"):
            idx = f" {event['index']}/{event['total']}"
        msg = event.get("message") or ""
        self.console.print(f"[cyan]chip-progress[/cyan] {who}{idx} [{status}] {label} - {msg}")


def _append_progress_jsonl(event: Dict[str, Any]) -> None:
    paths: List[Path] = []
    active_path = progress_path_for("")
    if active_path is not None:
        paths.append(active_path)
    run_id = str(event.get("run_id") or "")
    if run_id:
        external_path = run_dir_for(run_id) / "progress.jsonl"
        if external_path not in paths:
            paths.append(external_path)
    for path in paths:
        try:
            path.parent.mkdir(parents=True, exist_ok=True)
            with open(path, "a", encoding="utf-8") as fh:
                fh.write(json.dumps(event, ensure_ascii=False) + "\n")
        except Exception:
            pass


def _emit_web_event(event: Dict[str, Any]) -> None:
    try:
        from ..web.server import emit_event
        emit_event(f"chip_progress:{event.get('event_type', 'event')}", event)
    except Exception:
        pass
    try:
        from ..web.routers.orchestrator import record_chip_progress_event
        record_chip_progress_event(event)
    except Exception:
        pass


def _emit_cli_event(
    event: Dict[str, Any],
    *,
    cli_state: Any = None,
    quiet: bool = False,
    json_progress: bool = False,
) -> None:
    if quiet and not json_progress:
        return
    console = getattr(cli_state, "console", None) if cli_state is not None else None
    if console is None:
        return
    # WebConsole already receives the structured WebSocket event; printing every
    # event into chat logs makes the dashboard noisy.
    if console.__class__.__name__ == "WebConsole":
        return
    try:
        ChipProgressConsoleSink(console, json_progress=json_progress).emit(event)
    except Exception:
        pass
