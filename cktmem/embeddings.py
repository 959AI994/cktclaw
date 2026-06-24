"""
Semantic Memory — pluggable embedding backends.

Supports:
  - Jina Cloud API (JINA_API_KEY / CKTCLAW_JINA_KEY)
  - Local BGE via sentence-transformers (default local)
  - Legacy all-MiniLM-L6-v2 (minilm backend)

Configure via environment:
  CKTCLAW_EMBEDDING_BACKEND=auto|jina|bge|minilm
  CKTCLAW_EMBEDDING_MODEL=<model id override>
  JINA_API_KEY / CKTCLAW_JINA_KEY
"""

import logging
import os
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

_JINA_API_URL = "https://api.jina.ai/v1/embeddings"
_DEFAULT_JINA_MODEL = "jina-embeddings-v3"
_DEFAULT_BGE_MODEL = "BAAI/bge-small-zh-v1.5"
_DEFAULT_MINILM_MODEL = "all-MiniLM-L6-v2"

_local_encoder = None
_local_encoder_model: Optional[str] = None
_last_error: Optional[str] = None


def _set_error(msg: str) -> None:
    global _last_error
    _last_error = msg


def _clear_error() -> None:
    global _last_error
    _last_error = None


def _missing_dependency_from_error(err: str) -> Optional[str]:
    if "sentence_transformers" in err or "sentence-transformers" in err.lower():
        return "sentence-transformers"
    return None


def get_embedding_backend() -> str:
    """Resolved backend name: jina | bge | minilm."""
    backend = os.environ.get("CKTCLAW_EMBEDDING_BACKEND", "auto").strip().lower()
    if backend != "auto":
        return backend

    try:
        from ..api_credentials import get_jina_api_key
        if get_jina_api_key(required=False):
            return "jina"
    except Exception:
        pass

    return "bge"


def get_embedding_model_id() -> str:
    """Model identifier used for vector-store compatibility checks."""
    explicit = os.environ.get("CKTCLAW_EMBEDDING_MODEL", "").strip()
    if explicit:
        return explicit

    backend = get_embedding_backend()
    if backend == "jina":
        return _DEFAULT_JINA_MODEL
    if backend == "minilm":
        return _DEFAULT_MINILM_MODEL
    return _DEFAULT_BGE_MODEL


def warmup_embeddings() -> Dict[str, Any]:
    """Force-load the embedding backend (e.g. download BGE weights)."""
    _clear_error()
    vec = embed_text("warmup probe", task="retrieval.passage")
    return get_embedding_status(probe=False, probe_ok=vec is not None)


def get_embedding_status(
    *,
    probe: bool = True,
    probe_ok: Optional[bool] = None,
) -> Dict[str, Any]:
    """Status dict for dashboards / memory API."""
    backend = get_embedding_backend()
    model = get_embedding_model_id()

    if probe:
        probe_ok = embed_text("probe", task="retrieval.passage") is not None
    else:
        probe_ok = bool(probe_ok)

    error_detail = _last_error
    missing_dependency = _missing_dependency_from_error(error_detail or "")

    note = None
    if not probe_ok:
        if backend == "jina":
            note = (
                "Jina embedding unavailable. Set JINA_API_KEY in .env or "
                "switch CKTCLAW_EMBEDDING_BACKEND=bge for local models."
            )
        elif missing_dependency == "sentence-transformers":
            note = (
                "Local BGE requires sentence-transformers. "
                "Run: pip install sentence-transformers"
            )
        else:
            note = (
                "Local embedding unavailable. Install sentence-transformers "
                "(included in default setup)."
            )
            if _has_jina_key():
                note += (
                    " Or set CKTCLAW_EMBEDDING_BACKEND=jina in .env to use cloud embeddings."
                )

    return {
        "backend": backend,
        "model": model,
        "available": probe_ok,
        "note": note,
        "error_detail": error_detail,
        "missing_dependency": missing_dependency,
    }


def _has_jina_key() -> bool:
    try:
        from ..api_credentials import get_jina_api_key
        return bool(get_jina_api_key(required=False))
    except Exception:
        return False


def _get_local_encoder(model_name: str):
    """Lazy-load a sentence-transformers model."""
    global _local_encoder, _local_encoder_model
    if _local_encoder is not None and _local_encoder_model == model_name:
        return _local_encoder
    try:
        from sentence_transformers import SentenceTransformer
    except ImportError as e:
        _set_error(str(e))
        logger.info(
            "sentence-transformers not installed. "
            "Run setup.sh or: pip install sentence-transformers"
        )
        return None
    try:
        _local_encoder = SentenceTransformer(model_name)
        _local_encoder_model = model_name
        _clear_error()
        logger.debug("Loaded local embedding model: %s", model_name)
        return _local_encoder
    except Exception as e:
        _set_error(str(e))
        logger.warning("Failed to load embedding model %s: %s", model_name, e)
        return None


def _embed_jina(texts: List[str], task: str) -> Optional[List[List[float]]]:
    try:
        from ..api_credentials import get_jina_api_key
        api_key = get_jina_api_key(required=False)
    except Exception:
        api_key = None

    if not api_key:
        _set_error("JINA_API_KEY not configured")
        return None

    import requests

    model = get_embedding_model_id()
    payload: Dict[str, Any] = {
        "model": model,
        "input": texts,
        "embedding_type": "float",
        "normalized": True,
        "task": task,
    }
    try:
        resp = requests.post(
            _JINA_API_URL,
            headers={
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json",
            },
            json=payload,
            timeout=60,
        )
        resp.raise_for_status()
        data = resp.json().get("data", [])
        vectors = [item.get("embedding") for item in data]
        if not vectors or any(v is None for v in vectors):
            _set_error("Jina API returned empty embeddings")
            return None
        _clear_error()
        return vectors
    except Exception as e:
        _set_error(str(e))
        logger.warning("Jina embedding failed: %s", e)
        return None


def _embed_local(texts: List[str]) -> Optional[List[List[float]]]:
    model_name = get_embedding_model_id()
    encoder = _get_local_encoder(model_name)
    if encoder is None:
        return None
    try:
        vecs = encoder.encode(texts, show_progress_bar=False)
        _clear_error()
        return vecs.tolist()
    except Exception as e:
        _set_error(str(e))
        logger.warning("Local embedding failed: %s", e)
        return None


def embed_texts(texts: List[str], task: str = "retrieval.passage") -> Optional[List[List[float]]]:
    """Batch encode texts into embedding vectors."""
    if not texts:
        return []

    backend = get_embedding_backend()
    if backend == "jina":
        vecs = _embed_jina(texts, task=task)
        if vecs is not None:
            return vecs
        return _embed_local(texts)

    return _embed_local(texts)


def embed_text(text: str, task: str = "retrieval.passage") -> Optional[List[float]]:
    """Encode a single text into an embedding vector."""
    if not text:
        return None
    vecs = embed_texts([text], task=task)
    if not vecs:
        return None
    return vecs[0]


def cosine_similarity(a: List[float], b: List[float]) -> float:
    """Compute cosine similarity between two vectors."""
    import math
    dot = sum(x * y for x, y in zip(a, b))
    norm_a = math.sqrt(sum(x * x for x in a))
    norm_b = math.sqrt(sum(x * x for x in b))
    if norm_a == 0 or norm_b == 0:
        return 0.0
    return dot / (norm_a * norm_b)
