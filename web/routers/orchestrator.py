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
    status: str = "pending"
    current_stage: Optional[str] = None
    stage_index: int = 0
    stage_total: int = 0
    snapshot: Optional[dict] = None
    error: Optional[str] = None
    logs: List[str] = field(default_factory=list)
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


def _run_to_dict(state: OrchestratorRunState) -> dict:
    return {
        "run_id": state.run_id,
        "skill": state.skill,
        "task": state.task,
        "session_id": state.session_id,
        "status": state.status,
        "current_stage": state.current_stage,
        "stage_index": state.stage_index,
        "stage_total": state.stage_total,
        "snapshot": state.snapshot,
        "error": state.error,
        "logs": state.logs[-50:],
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
        if isinstance(result, list):
            for item in result:
                if isinstance(item, dict) and "text" in item:
                    rendered_parts.append(str(item["text"]))
        else:
            rendered_parts.append(str(result))

        assistant_content = "\n\n".join(p for p in rendered_parts if p.strip())
        await _persist_messages(state.session_id, state.skill, state.task, assistant_content)

        state.snapshot = {"output": assistant_content[:2000]}
        state.status = "completed"
        state.finished_at = datetime.now().isoformat()
        _emit("orchestrator:done", {
            "run_id": state.run_id,
            "skill": state.skill,
            "status": "completed",
        })
    except asyncio.CancelledError:
        state.status = "aborted"
        state.error = "Aborted by user"
        state.finished_at = datetime.now().isoformat()
        _emit("orchestrator:failed", {
            "run_id": state.run_id,
            "skill": state.skill,
            "error": state.error,
        })
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
        })
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

    skill_name = body.skill.strip()
    if not skill_name.startswith("chip-"):
        raise HTTPException(status_code=400, detail="Only chip-* specialist skills are supported")

    if _active_run_count() >= MAX_CONCURRENT_RUNS:
        raise HTTPException(
            status_code=429,
            detail=f"Max concurrent orchestrator runs ({MAX_CONCURRENT_RUNS}) reached",
        )

    run_id = f"orch-{uuid.uuid4().hex[:12]}"
    session_id = body.session_id or uuid.uuid4().hex[:16]

    task_text = body.task.strip()
    upload_session = body.session_id or session_id
    if body.attachment_ids:
        from ..uploads import build_attachment_context, resolve_uploads
        uploads = resolve_uploads(upload_session, body.attachment_ids)
        block = build_attachment_context(uploads)
        if block:
            task_text = task_text + block

    state = OrchestratorRunState(
        run_id=run_id,
        skill=skill_name,
        task=task_text,
        session_id=session_id,
    )
    _orchestrator_runs[run_id] = state

    task = asyncio.create_task(_execute_orchestrator(state))
    _orchestrator_tasks[run_id] = task

    return {"run_id": run_id, "status": "started", "session_id": session_id}


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
