"""Session and memory management endpoints."""
import logging

from fastapi import APIRouter, HTTPException, Query

router = APIRouter(prefix="/api/sessions", tags=["sessions"])
logger = logging.getLogger(__name__)


def _get_storage():
    from ..deps import get_web_storage
    return get_web_storage()


def _message_to_dict(m) -> dict:
    if isinstance(m, dict):
        d = m
    elif hasattr(m, "model_dump"):
        d = m.model_dump()
    elif hasattr(m, "dict"):
        d = m.dict()
    else:
        role = getattr(m, "role", "user")
        if hasattr(role, "value"):
            role = role.value
        d = {
            "role": role,
            "content": getattr(m, "content", ""),
            "created_at": getattr(m, "created_at", None),
        }
    role = d.get("role", "user")
    if hasattr(role, "value"):
        role = role.value
    return {
        "role": role,
        "content": d.get("content", ""),
        "created_at": d.get("created_at"),
        "tool_calls": d.get("tool_calls"),
    }


@router.get("")
async def list_sessions(limit: int = Query(20, ge=1, le=100)):
    storage = _get_storage()
    from . import resolve_async
    try:
        sessions = resolve_async(storage.list_sessions(limit=limit)) or []
        result = []
        for s in sessions:
            sid = s.get("session_id", "")
            msgs = resolve_async(storage.get_recent_messages(sid, max_rounds=1000, after_last_boundary=False))
            result.append({
                **s,
                "id": sid,
                "message_count": len(msgs) if msgs else 0,
            })
        return result
    except Exception as e:
        logger.error(f"list_sessions failed: {e}")
        return []


@router.get("/{session_id}")
async def get_session(session_id: str):
    storage = _get_storage()
    from . import resolve_async
    try:
        session = resolve_async(storage.get_session(session_id))
        if session is None:
            raise HTTPException(status_code=404, detail="Session not found")
        return session
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"get_session failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.delete("/{session_id}")
async def delete_session(session_id: str):
    storage = _get_storage()
    from . import resolve_async
    try:
        ok = resolve_async(storage.delete_session(session_id))
        if ok:
            return {"status": "deleted"}
        raise HTTPException(status_code=404, detail="Session not found")
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"delete_session failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/{session_id}/messages")
async def get_messages(
    session_id: str,
    layer: str = Query("turn", description="turn|session|project|all"),
    limit: int = Query(50, ge=1, le=200),
):
    storage = _get_storage()
    from . import resolve_async
    try:
        if layer == "all":
            messages = resolve_async(storage.get_messages(session_id, limit=limit))
        else:
            messages = resolve_async(
                storage.get_recent_messages(session_id, max_rounds=limit, after_last_boundary=True)
            )
        if messages and len(messages) > limit:
            messages = messages[-limit:]
        return [_message_to_dict(m) for m in (messages or [])]
    except Exception as e:
        logger.error(f"get_messages failed: {e}")
        return []


@router.get("/{session_id}/memories")
async def get_memories(session_id: str):
    storage = _get_storage()
    from . import resolve_async
    try:
        return resolve_async(storage.get_session_memories(session_id)) or []
    except Exception as e:
        logger.error(f"get_memories failed: {e}")
        return []


@router.get("/{session_id}/context_stats")
async def get_context_stats_endpoint(session_id: str):
    from ..deps import get_web_context_manager
    from . import resolve_async

    ctx = get_web_context_manager()
    try:
        return resolve_async(ctx.get_context_stats(session_id))
    except Exception as e:
        logger.error(f"context_stats failed: {e}")
        return {}
