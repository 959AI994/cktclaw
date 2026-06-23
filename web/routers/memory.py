"""Vector store memory search endpoints."""
import logging

from fastapi import APIRouter, Query
from pydantic import BaseModel

router = APIRouter(prefix="/api/memory", tags=["memory"])
logger = logging.getLogger(__name__)


class SearchRequest(BaseModel):
    query: str
    top_k: int = 5


class AddRequest(BaseModel):
    text: str
    metadata: dict | None = None


def _get_vector_store():
    try:
        from ...cktmem.vector_store import VectorStore
        return VectorStore()
    except Exception:
        return None


def _get_storage():
    from ..deps import get_web_storage
    return get_web_storage()


@router.get("")
async def list_memory(limit: int = Query(20, ge=1, le=100)):
    vs = _get_vector_store()
    vector_count = 0
    entries = []
    note = None
    if vs is None:
        note = "Vector store not available (install sentence-transformers)"
    else:
        try:
            entries = vs.list_all() if hasattr(vs, "list_all") else []
            vector_count = len(entries)
            if entries and len(entries) > limit:
                entries = entries[:limit]
        except Exception as e:
            logger.error(f"list_memory failed: {e}")
            note = str(e)

    session_count = 0
    try:
        from . import resolve_async
        storage = _get_storage()
        sessions = resolve_async(storage.list_sessions(limit=5)) or []
        for s in sessions:
            sid = s.get("session_id", "")
            mems = resolve_async(storage.get_session_memories(sid)) or []
            session_count += len(mems)
    except Exception:
        pass

    return {
        "entries": entries,
        "note": note,
        "sources": {"vector": vector_count, "session": session_count},
    }


@router.get("/session")
async def list_session_memory(
    session_id: str = Query(..., description="CktMem session id"),
):
    from . import resolve_async

    storage = _get_storage()
    try:
        memories = resolve_async(storage.get_session_memories(session_id)) or []
        return {"entries": memories, "session_id": session_id, "count": len(memories)}
    except Exception as e:
        logger.error(f"list_session_memory failed: {e}")
        return {"entries": [], "session_id": session_id, "error": str(e)}


@router.post("/search")
async def search_memory(body: SearchRequest):
    vs = _get_vector_store()
    if vs is None:
        return {"results": [], "note": "Vector store not available"}
    try:
        results = vs.search(body.query, top_k=body.top_k)
        formatted = []
        for r in results:
            if isinstance(r, tuple) and len(r) >= 2:
                formatted.append({"text": r[0], "score": round(float(r[1]), 4)})
            elif isinstance(r, dict):
                formatted.append(r)
        return {"results": formatted}
    except Exception as e:
        logger.error(f"search_memory failed: {e}")
        return {"results": [], "error": str(e)}


@router.post("/add")
async def add_memory(body: AddRequest):
    vs = _get_vector_store()
    if vs is None:
        return {"status": "error", "note": "Vector store not available"}
    try:
        vs.add(body.text, body.metadata or {})
        return {"status": "added"}
    except Exception as e:
        logger.error(f"add_memory failed: {e}")
        return {"status": "error", "error": str(e)}
