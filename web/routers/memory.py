"""Vector store memory search endpoints."""
import logging

from fastapi import APIRouter, Query
from pydantic import BaseModel

router = APIRouter(prefix="/api/memory", tags=["memory"])
logger = logging.getLogger(__name__)

_EMBEDDINGS_NOTE = (
    "Semantic memory needs an embedding backend. Options:\n"
    "  • Set JINA_API_KEY in .env (cloud, recommended)\n"
    "  • Or use local BGE via sentence-transformers (installed by setup.sh)"
)


def _embedding_status() -> dict:
    try:
        from ...cktmem.embeddings import get_embedding_status
        return get_embedding_status()
    except Exception:
        return {"backend": "unknown", "model": "", "available": False, "note": _EMBEDDINGS_NOTE}


def _embeddings_available() -> bool:
    return bool(_embedding_status().get("available"))


class SearchRequest(BaseModel):
    query: str
    top_k: int = 5


class AddRequest(BaseModel):
    text: str
    metadata: dict | None = None


class SessionMemoryRequest(BaseModel):
    session_id: str
    topic: str
    summary: str
    content: str
    memory_type: str = "general"


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
    status = _embedding_status()
    embeddings_available = bool(status.get("available"))
    vector_count = 0
    entries = []
    note = status.get("note")

    if vs is None:
        note = note or _EMBEDDINGS_NOTE
    else:
        try:
            entries = vs.list_entries(limit=limit)
            vector_count = vs.size
            if not embeddings_available:
                note = note or _EMBEDDINGS_NOTE
        except Exception as e:
            logger.error(f"list_memory failed: {e}")
            note = str(e)

    session_count = 0
    try:
        from . import resolve_async
        storage = _get_storage()
        session_count = resolve_async(storage.count_session_memories()) or 0
    except Exception:
        pass

    return {
        "entries": entries,
        "note": note,
        "embeddings_available": embeddings_available,
        "embedding_backend": status.get("backend"),
        "embedding_model": status.get("model"),
        "error_detail": status.get("error_detail"),
        "missing_dependency": status.get("missing_dependency"),
        "sources": {"vector": vector_count, "session": session_count},
    }


@router.post("/warmup")
async def warmup_memory():
    try:
        from ...cktmem.embeddings import warmup_embeddings
        status = warmup_embeddings()
        return {"status": "ok" if status.get("available") else "error", **status}
    except Exception as e:
        logger.error(f"warmup_memory failed: {e}")
        return {
            "status": "error",
            "available": False,
            "error_detail": str(e),
            "note": str(e),
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


@router.get("/session/all")
async def list_all_session_memories(limit: int = Query(50, ge=1, le=200)):
    from . import resolve_async

    storage = _get_storage()
    try:
        memories = resolve_async(storage.list_all_session_memories(limit=limit)) or []
        return {"entries": memories, "count": len(memories)}
    except Exception as e:
        logger.error(f"list_all_session_memories failed: {e}")
        return {"entries": [], "error": str(e)}


@router.post("/session")
async def save_session_memory(body: SessionMemoryRequest):
    from . import resolve_async

    storage = _get_storage()
    topic = body.topic.strip()
    summary = body.summary.strip()
    content = body.content.strip()
    if not body.session_id or not topic or not summary or not content:
        return {"status": "error", "error": "session_id, topic, summary, and content are required"}

    try:
        resolve_async(
            storage.save_session_memory(
                session_id=body.session_id,
                topic=topic,
                summary=summary,
                content=content,
                memory_type=body.memory_type or "general",
            )
        )
        return {"status": "saved", "session_id": body.session_id, "topic": topic}
    except Exception as e:
        logger.error(f"save_session_memory failed: {e}")
        return {"status": "error", "error": str(e)}


@router.post("/search")
async def search_memory(body: SearchRequest):
    vs = _get_vector_store()
    status = _embedding_status()
    embeddings_available = bool(status.get("available"))
    if vs is None:
        return {
            "results": [],
            "note": status.get("note") or _EMBEDDINGS_NOTE,
            "embeddings_available": False,
            "error_detail": status.get("error_detail"),
            "missing_dependency": status.get("missing_dependency"),
        }
    if not embeddings_available:
        return {
            "results": [],
            "note": status.get("note") or _EMBEDDINGS_NOTE,
            "embeddings_available": False,
            "error_detail": status.get("error_detail"),
            "missing_dependency": status.get("missing_dependency"),
        }
    try:
        results = vs.search(body.query, top_k=body.top_k)
        formatted = []
        for r in results:
            if isinstance(r, tuple) and len(r) >= 2:
                item = {"text": r[0], "score": round(float(r[1]), 4)}
                if len(r) >= 3 and isinstance(r[2], dict):
                    item["metadata"] = r[2]
                formatted.append(item)
            elif isinstance(r, dict):
                formatted.append(r)
        return {"results": formatted, "embeddings_available": True}
    except Exception as e:
        logger.error(f"search_memory failed: {e}")
        return {"results": [], "error": str(e), "embeddings_available": embeddings_available}


@router.post("/add")
async def add_memory(body: AddRequest):
    vs = _get_vector_store()
    if vs is None:
        return {"status": "error", "note": _EMBEDDINGS_NOTE}
    if not _embeddings_available():
        return {"status": "error", "note": _EMBEDDINGS_NOTE}
    try:
        ok = vs.add(body.text, body.metadata or {})
        if not ok:
            return {"status": "error", "note": _EMBEDDINGS_NOTE}
        return {"status": "added"}
    except Exception as e:
        logger.error(f"add_memory failed: {e}")
        return {"status": "error", "error": str(e)}
