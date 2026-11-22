"""Web-layer CLIState adapter for orchestrator and skill executors."""

from __future__ import annotations

import re
import uuid
from dataclasses import dataclass, field
from typing import Any, Optional

from rich.console import Console


def _emit(event_type: str, data: dict) -> None:
    try:
        from .server import emit_event
        emit_event(event_type, data)
    except Exception:
        pass
    try:
        from .routers.orchestrator import emit_chat_progress_from_event, update_run_state
        update_run_state(event_type, data)
        emit_chat_progress_from_event(event_type, data)
    except Exception:
        pass


_STAGE_RE = re.compile(r"Stage:\s*(\S+)")


class WebConsole:
    """Rich Console wrapper that forwards output to WebSocket events."""

    def __init__(self, run_id: str = "", session_id: str = ""):
        self.run_id = run_id
        self.session_id = session_id
        self._console = Console(force_terminal=False, width=120, highlight=False)

    def _base_payload(self) -> dict:
        payload: dict = {"run_id": self.run_id}
        if self.session_id:
            payload["session_id"] = self.session_id
        return payload

    def emit_stage(self, stage: str, index: int, total: int) -> None:
        """Explicit stage notification (used by OrchestratorEngine)."""
        _emit(
            "orchestrator:stage_start",
            {
                **self._base_payload(),
                "stage": stage,
                "index": index,
                "total": total,
            },
        )
        try:
            from ..runtime.chip_progress import publish_chip_progress
            publish_chip_progress(
                event_type="phase_started",
                cli_state=self,
                phase=stage,
                status="running",
                index=index,
                total=total,
                message=f"Stage: {stage} ({index}/{total})",
            )
        except Exception:
            pass

    def print(self, *args, **kwargs) -> None:
        with self._console.capture() as capture:
            self._console.print(*args, **kwargs)
        text = capture.get().rstrip()
        if not text:
            return

        payload = {**self._base_payload(), "message": text}
        _emit("orchestrator:log", payload)

        stage_match = _STAGE_RE.search(text)
        has_stage_marker = "━━━ Stage:" in text or (
            "Stage:" in text and re.search(r"\(\d+/\d+\)", text)
        )
        if has_stage_marker and stage_match:
            stage = stage_match.group(1)
            idx_match = re.search(r"\((\d+)/(\d+)\)", text)
            _emit(
                "orchestrator:stage_start",
                {
                    **self._base_payload(),
                    "stage": stage,
                    "index": int(idx_match.group(1)) if idx_match else 0,
                    "total": int(idx_match.group(2)) if idx_match else 0,
                },
            )

    def __getattr__(self, name: str) -> Any:
        return getattr(self._console, name)


@dataclass
class WebCLIState:
    """Minimal CLIState for web orchestrator runs."""

    session_id: str = field(default_factory=lambda: uuid.uuid4().hex[:16])
    current_engine: str = "deepseek"
    storage: Any = None
    console: Optional[WebConsole] = None
    llm_analyzer: Any = None
    _tool_manifest: Any = None
    _mcp_manager: Any = None
    run_id: str = ""

    def __post_init__(self) -> None:
        if self.storage is None:
            from .deps import get_web_storage
            self.storage = get_web_storage()
        if self.console is None:
            self.console = WebConsole(run_id=self.run_id, session_id=self.session_id)
        elif isinstance(self.console, WebConsole):
            if self.run_id:
                self.console.run_id = self.run_id
            if self.session_id:
                self.console.session_id = self.session_id

        try:
            from ..llm import get_model_router
            router = get_model_router()
            router.initialize()
            if router.current_name:
                self.current_engine = router.current_name
        except Exception:
            pass


def create_web_cli_state(session_id: Optional[str] = None, run_id: str = "") -> WebCLIState:
    sid = session_id or uuid.uuid4().hex[:16]
    return WebCLIState(session_id=sid, run_id=run_id)
