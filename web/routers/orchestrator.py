"""Orchestrator run endpoints for chip-design specialists."""

from __future__ import annotations

import asyncio
import logging
import uuid
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

router = APIRouter(prefix="/api/orchestrator", tags=["orchestrator"])
logger = logging.getLogger(__name__)

MAX_CONCURRENT_RUNS = 2
_orchestrator_runs: Dict[str, "OrchestratorRunState"] = {}
_orchestrator_tasks: Dict[str, asyncio.Task] = {}


@dataclass
class OrchestratorRunState:
    run_id: str
    skill: str
    task: str
    session_id: str
    intent: Optional[dict] = None
    route_rationale: str = ""
    status: str = "pending"
    current_stage: Optional[str] = None
    stage_index: int = 0
    stage_total: int = 0
    snapshot: Optional[dict] = None
    error: Optional[str] = None
    logs: List[str] = field(default_factory=list)
    progress_events: List[dict] = field(default_factory=list)
    agent_plan: List[dict] = field(default_factory=list)
    artifact_index: List[str] = field(default_factory=list)
    qor_summary: Dict[str, Any] = field(default_factory=dict)
    coverage_summary: Dict[str, Any] = field(default_factory=dict)
    fix_requests: List[dict] = field(default_factory=list)
    started_at: str = field(default_factory=lambda: datetime.now().isoformat())
    finished_at: Optional[str] = None


class RunRequest(BaseModel):
    skill: str = Field(..., min_length=1)
    task: str = Field(..., min_length=1)
    session_id: Optional[str] = None
    auto_confirm: bool = True
    attachment_ids: Optional[list[str]] = None


def _emit(event_type: str, data: dict) -> None:
    try:
        from ..server import emit_event
        emit_event(event_type, data)
    except Exception:
        pass
    update_run_state(event_type, data)
    emit_chat_progress_from_event(event_type, data)


def emit_chat_progress_from_event(event_type: str, data: dict) -> None:
    """Bridge orchestrator system events to chat-channel WS messages."""
    run_id = data.get("run_id")
    if not run_id:
        return
    state = _orchestrator_runs.get(run_id)
    if state is None:
        return

    from ..server import broadcast_chat

    if event_type == "orchestrator:started":
        broadcast_chat(state.session_id, {
            "type": "chat:orchestrator_progress",
            "run_id": run_id,
            "skill": state.skill,
            "task": state.task[:200],
            "status": "running",
            "log_delta": "Orchestrator started.",
        })
    elif event_type == "orchestrator:log":
        msg = data.get("message", "")
        if msg:
            broadcast_chat(state.session_id, {
                "type": "chat:orchestrator_progress",
                "run_id": run_id,
                "skill": state.skill,
                "status": state.status,
                "stage": state.current_stage,
                "stage_index": state.stage_index,
                "stage_total": state.stage_total,
                "log_delta": msg,
                "logs_tail": state.logs[-30:],
            })
    elif event_type == "orchestrator:stage_start":
        broadcast_chat(state.session_id, {
            "type": "chat:orchestrator_progress",
            "run_id": run_id,
            "skill": state.skill,
            "status": "running",
            "stage": data.get("stage"),
            "stage_index": data.get("index"),
            "stage_total": data.get("total"),
            "log_delta": f"Stage: {data.get('stage')} ({data.get('index')}/{data.get('total')})",
        })


async def emit_chat_done(
    state: OrchestratorRunState,
    summary: str,
    *,
    artifacts: Optional[List[dict]] = None,
    snapshot: Optional[dict] = None,
) -> None:
    from ..server import _broadcast_chat
    await _broadcast_chat(state.session_id, {
        "type": "chat:orchestrator_done",
        "run_id": state.run_id,
        "skill": state.skill,
        "summary": summary,
        "artifacts": artifacts or [],
        "snapshot": snapshot if snapshot is not None else state.snapshot,
    })


async def emit_chat_failed(state: OrchestratorRunState, error: str) -> None:
    from ..server import _broadcast_chat
    await _broadcast_chat(state.session_id, {
        "type": "chat:orchestrator_failed",
        "run_id": state.run_id,
        "skill": state.skill,
        "error": error,
    })


def _active_run_count() -> int:
    return sum(1 for r in _orchestrator_runs.values() if r.status in ("pending", "running"))


def update_run_state(event_type: str, data: dict) -> None:
    """Keep in-memory run state in sync with WebSocket events."""
    run_id = data.get("run_id")
    if not run_id:
        return
    state = _orchestrator_runs.get(run_id)
    if state is None:
        return

    if event_type == "orchestrator:stage_start":
        state.current_stage = data.get("stage")
        state.stage_index = int(data.get("index") or 0)
        state.stage_total = int(data.get("total") or 0)
    elif event_type == "orchestrator:log":
        msg = data.get("message", "")
        if msg:
            state.logs.append(msg)
            if len(state.logs) > 200:
                state.logs = state.logs[-200:]
    elif event_type == "orchestrator:done":
        state.status = "completed"
        state.finished_at = datetime.now().isoformat()
    elif event_type == "orchestrator:failed":
        state.status = "failed" if state.status != "aborted" else "aborted"
        state.error = data.get("error")
        state.finished_at = datetime.now().isoformat()


def record_chip_progress_event(event: dict) -> None:
    """Attach structured chip progress to the matching web orchestrator run."""
    run_id = event.get("run_id")
    if not run_id:
        return
    state = _orchestrator_runs.get(str(run_id))
    if state is None:
        return

    state.progress_events.append(event)
    if len(state.progress_events) > 500:
        state.progress_events = state.progress_events[-500:]

    event_type = str(event.get("event_type") or "")
    if event_type in {"run_started", "phase_started", "skill_started"}:
        state.status = "running"
        state.current_stage = event.get("phase") or event.get("skill") or state.current_stage
        state.stage_index = int(event.get("index") or state.stage_index or 0)
        state.stage_total = int(event.get("total") or state.stage_total or 0)
    elif event_type in {"phase_completed", "skill_completed"}:
        state.current_stage = event.get("phase") or event.get("skill") or state.current_stage
        state.stage_index = int(event.get("index") or state.stage_index or 0)
        state.stage_total = int(event.get("total") or state.stage_total or 0)
    elif event_type in {"run_completed", "run_failed"}:
        state.status = "completed" if event_type == "run_completed" else "failed"
        state.finished_at = datetime.now().isoformat()

    msg = event.get("message")
    phase = event.get("phase") or event.get("skill") or event_type
    if msg:
        state.logs.append(f"[{phase}] {msg}")
        if len(state.logs) > 200:
            state.logs = state.logs[-200:]

    metadata = event.get("metadata") if isinstance(event.get("metadata"), dict) else {}
    if isinstance(metadata.get("agent_plan"), list):
        state.agent_plan = metadata["agent_plan"]

    for path in event.get("artifacts") or []:
        if isinstance(path, str) and path not in state.artifact_index:
            state.artifact_index.append(path)
    if len(state.artifact_index) > 200:
        state.artifact_index = state.artifact_index[-200:]

    if isinstance(event.get("qor"), dict) and event["qor"]:
        state.qor_summary = event["qor"]
    if isinstance(event.get("coverage"), dict) and event["coverage"]:
        state.coverage_summary = event["coverage"]
    if isinstance(event.get("fix_request"), dict) and event["fix_request"]:
        state.fix_requests.append(event["fix_request"])
        state.fix_requests = state.fix_requests[-50:]

    try:
        from ..server import broadcast_chat
        broadcast_chat(state.session_id, {
            "type": "chat:orchestrator_progress",
            "run_id": run_id,
            "skill": state.skill,
            "status": state.status,
            "stage": state.current_stage,
            "stage_index": state.stage_index,
            "stage_total": state.stage_total,
            "log_delta": f"{event.get('agent') or event.get('skill') or 'chip'}: {event.get('message') or event_type}",
            "logs_tail": state.logs[-30:],
        })
    except Exception:
        pass


def _run_to_dict(state: OrchestratorRunState) -> dict:
    return {
        "run_id": state.run_id,
        "skill": state.skill,
        "task": state.task,
        "session_id": state.session_id,
        "intent": state.intent,
        "route_rationale": state.route_rationale,
        "status": state.status,
        "current_stage": state.current_stage,
        "stage_index": state.stage_index,
        "stage_total": state.stage_total,
        "snapshot": state.snapshot,
        "error": state.error,
        "logs": state.logs[-50:],
        "progress_events": state.progress_events[-300:],
        "agent_plan": state.agent_plan,
        "artifact_index": state.artifact_index[-100:],
        "qor_summary": state.qor_summary,
        "coverage_summary": state.coverage_summary,
        "fix_requests": state.fix_requests[-50:],
        "started_at": state.started_at,
        "finished_at": state.finished_at,
    }


async def _persist_messages(session_id: str, skill: str, task: str, assistant_content: str) -> None:
    try:
        from ...cktmem.models import ContextLayer, MessageRole, MessageType
        from ..deps import get_web_storage

        storage = get_web_storage()
        user_content = f"/{skill} {task}".strip()
        await storage.add_message(
            session_id=session_id,
            role=MessageRole.USER,
            content=user_content,
            msg_type=MessageType.CHAT,
            layer=ContextLayer.TURN,
        )
        await storage.add_message(
            session_id=session_id,
            role=MessageRole.ASSISTANT,
            content=assistant_content,
            msg_type=MessageType.CHAT,
            layer=ContextLayer.TURN,
        )
    except Exception as e:
        logger.warning(f"Failed to persist orchestrator messages: {e}")


async def _execute_orchestrator(state: OrchestratorRunState) -> None:
    import os

    from ..bootstrap import ensure_runtime_bootstrapped
    from ..cli_state import create_web_cli_state
    from ...harness import get_skill_registry
    from ...runtime.run_context import new_run

    os.environ["CKTCLAW_ORCHESTRATOR_AUTO_CONFIRM"] = "1"

    ensure_runtime_bootstrapped()
    state.status = "running"
    _emit("orchestrator:started", {
        "run_id": state.run_id,
        "skill": state.skill,
        "task": state.task[:200],
        "session_id": state.session_id,
    })
    _emit("orchestrator:log", {
        "run_id": state.run_id,
        "session_id": state.session_id,
        "message": "Initializing orchestrator (MCP, tools)...",
    })

    run_ctx = new_run(kind="orchestrator")
    cli_state = create_web_cli_state(session_id=state.session_id, run_id=state.run_id)

    try:
        registry = get_skill_registry()
        skill = await registry.get_skill(state.skill)
        if skill is None or not skill.executor:
            raise ValueError(f"Skill '{state.skill}' not found or has no executor")

        with run_ctx.activate():
            result = await skill.executor(state.task.strip(), {"cli_state": cli_state})

        rendered_parts: List[str] = []
        orchestrator_snapshot: Optional[dict] = None
        if isinstance(result, list):
            for item in result:
                if not isinstance(item, dict):
                    continue
                if item.get("type") == "orchestrator_result":
                    orchestrator_snapshot = item.get("snapshot")
                elif item.get("type") == "multi_agent_result":
                    orchestrator_snapshot = item.get("result")
                elif "text" in item:
                    rendered_parts.append(str(item["text"]))
        else:
            rendered_parts.append(str(result))

        assistant_content = "\n\n".join(p for p in rendered_parts if p.strip())
        await _persist_messages(state.session_id, state.skill, state.task, assistant_content)

        artifacts: List[dict] = []
        if isinstance(orchestrator_snapshot, dict):
            raw_artifacts = orchestrator_snapshot.get("artifacts") or []
            artifacts = [a for a in raw_artifacts if isinstance(a, dict)]
            state.snapshot = orchestrator_snapshot
        else:
            state.snapshot = {"output": assistant_content}
        state.status = "completed"
        state.finished_at = datetime.now().isoformat()
        _emit("orchestrator:done", {
            "run_id": state.run_id,
            "skill": state.skill,
            "status": "completed",
            "session_id": state.session_id,
        })
        await emit_chat_done(
            state,
            assistant_content,
            artifacts=artifacts,
            snapshot=state.snapshot,
        )
    except asyncio.CancelledError:
        state.status = "aborted"
        state.error = "Aborted by user"
        state.finished_at = datetime.now().isoformat()
        _emit("orchestrator:failed", {
            "run_id": state.run_id,
            "skill": state.skill,
            "error": state.error,
            "session_id": state.session_id,
        })
        await emit_chat_failed(state, state.error)
        raise
    except Exception as e:
        logger.exception(f"Orchestrator run {state.run_id} failed")
        state.status = "failed"
        state.error = str(e)
        state.finished_at = datetime.now().isoformat()
        _emit("orchestrator:failed", {
            "run_id": state.run_id,
            "skill": state.skill,
            "error": state.error,
            "session_id": state.session_id,
        })
        await emit_chat_failed(state, state.error)
    finally:
        _orchestrator_tasks.pop(state.run_id, None)


@router.get("/runs")
async def list_runs():
    return [_run_to_dict(r) for r in sorted(
        _orchestrator_runs.values(),
        key=lambda x: x.started_at,
        reverse=True,
    )]


@router.post("/run")
async def start_run(body: RunRequest):
    from ..bootstrap import ensure_runtime_bootstrapped

    ensure_runtime_bootstrapped()

    try:
        return await launch_orchestrator_from_chat(
            skill=body.skill,
            task=body.task,
            session_id=body.session_id,
            attachment_ids=body.attachment_ids,
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    except RuntimeError as e:
        raise HTTPException(status_code=429, detail=str(e)) from e


async def launch_orchestrator_from_chat(
    *,
    skill: str,
    task: str,
    session_id: Optional[str] = None,
    attachment_ids: Optional[list[str]] = None,
    intent: Optional[dict] = None,
    route_rationale: str = "",
) -> dict:
    """Start an orchestrator run (shared by REST API and WebSocket chat confirm)."""
    skill_name = skill.strip()
    if not skill_name.startswith("chip-"):
        raise ValueError("Only chip-* specialist skills are supported (including chip-system)")

    if _active_run_count() >= MAX_CONCURRENT_RUNS:
        raise RuntimeError(f"Max concurrent orchestrator runs ({MAX_CONCURRENT_RUNS}) reached")

    run_id = f"orch-{uuid.uuid4().hex[:12]}"
    resolved_session = session_id or uuid.uuid4().hex[:16]

    task_text = task.strip()
    if intent is None:
        try:
            from ...handlers.intent_router import resolve_chip_intent
            resolved_intent = resolve_chip_intent(task_text)
            if resolved_intent.is_chip_task:
                intent = resolved_intent.to_dict()
                route_rationale = route_rationale or resolved_intent.rationale
        except Exception:
            pass
    upload_session = session_id or resolved_session
    if attachment_ids:
        from ..uploads import build_attachment_context, resolve_uploads
        uploads = resolve_uploads(upload_session, attachment_ids)
        block = build_attachment_context(uploads)
        if block:
            task_text = task_text + block

    state = OrchestratorRunState(
        run_id=run_id,
        skill=skill_name,
        task=task_text,
        session_id=resolved_session,
        intent=intent,
        route_rationale=route_rationale,
    )
    _orchestrator_runs[run_id] = state

    bg_task = asyncio.create_task(_execute_orchestrator(state))
    _orchestrator_tasks[run_id] = bg_task

    return {
        "run_id": run_id,
        "status": "started",
        "session_id": resolved_session,
        "skill": skill_name,
        "task": task_text,
        "intent": intent,
        "route_rationale": route_rationale,
    }


@router.get("/runs/{run_id}")
async def get_run(run_id: str):
    state = _orchestrator_runs.get(run_id)
    if state is None:
        raise HTTPException(status_code=404, detail="Run not found")
    return _run_to_dict(state)


@router.post("/runs/{run_id}/abort")
async def abort_run(run_id: str):
    state = _orchestrator_runs.get(run_id)
    if state is None:
        raise HTTPException(status_code=404, detail="Run not found")

    task = _orchestrator_tasks.get(run_id)
    if task and not task.done():
        task.cancel()
        try:
            await task
        except asyncio.CancelledError:
            pass
        return {"status": "aborted"}

    if state.status in ("completed", "failed", "aborted"):
        return {"status": state.status}

    raise HTTPException(status_code=400, detail="Run is not active")
