"""Agent management endpoints."""
import logging
from typing import Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

router = APIRouter(prefix="/api/agents", tags=["agents"])
logger = logging.getLogger(__name__)


class SpawnRequest(BaseModel):
    name: str
    task: str
    system_prompt: Optional[str] = None
    model: Optional[str] = None
    allowed_tools: Optional[list[str]] = None


class StopRequest(BaseModel):
    reason: str = "User requested"


def _get_runtime():
    from ...agents import get_agent_runtime
    return get_agent_runtime()


def _emit(event_type: str, data: dict):
    try:
        from ..server import emit_event
        emit_event(event_type, data)
    except Exception:
        pass


@router.get("")
async def list_agents():
    runtime = _get_runtime()
    try:
        return runtime.list_agents()
    except Exception as e:
        logger.error(f"list_agents failed: {e}")
        return []


@router.post("")
async def spawn_agent(body: SpawnRequest):
    runtime = _get_runtime()
    try:
        agent_id = runtime.spawn_worker(
            name=body.name,
            task=body.task,
            system_prompt=body.system_prompt,
            allowed_tools=body.allowed_tools,
            model=body.model,
        )
        _emit("agent:spawned", {"agent_id": agent_id, "name": body.name, "task": body.task[:200]})
        return {"agent_id": agent_id, "status": "spawned"}
    except Exception as e:
        logger.error(f"spawn_agent failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/{agent_id}")
async def get_agent(agent_id: str):
    runtime = _get_runtime()
    try:
        status = runtime.get_status(agent_id)
        if status is None:
            raise HTTPException(status_code=404, detail="Agent not found")
        return status
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"get_agent failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/{agent_id}/stop")
async def stop_agent(agent_id: str, body: StopRequest = StopRequest()):
    runtime = _get_runtime()
    try:
        ok = runtime.stop_agent(agent_id, reason=body.reason)
        if ok:
            _emit("agent:stopped", {"agent_id": agent_id, "reason": body.reason})
            return {"status": "stopped"}
        else:
            raise HTTPException(status_code=404, detail="Agent not found or already stopped")
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"stop_agent failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))
