"""
Semantic Memory — embedding-based retrieval for relevant context.

Uses sentence-transformers for lightweight embeddings and a simple
numpy-based vector store (no heavy dependencies like ChromaDB by default).
Falls back gracefully when sentence-transformers is not installed.
"""

import json
import logging
import os
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)

# Lazy-loaded model
_encoder = None
_EMBED_DIM = 384  # all-MiniLM-L6-v2 output dimension


def _get_encoder():
    """Lazy-load the sentence transformer encoder."""
    global _encoder
    if _encoder is None:
        try:
            from sentence_transformers import SentenceTransformer
            _encoder = SentenceTransformer("all-MiniLM-L6-v2")
            logger.debug("Loaded sentence-transformers model: all-MiniLM-L6-v2")
        except ImportError:
            logger.info(
                "sentence-transformers not installed. "
                "Semantic memory disabled. Install: pip install sentence-transformers"
            )
            return None
    return _encoder


def embed_text(text: str) -> Optional[List[float]]:
    """Encode text into an embedding vector."""
    encoder = _get_encoder()
    if encoder is None:
        return None
    try:
        vec = encoder.encode(text, show_progress_bar=False)
        return vec.tolist()
    except Exception as e:
        logger.warning(f"Embedding failed: {e}")
        return None


def embed_texts(texts: List[str]) -> Optional[List[List[float]]]:
    """Batch encode texts into embedding vectors."""
    encoder = _get_encoder()
    if encoder is None:
        return None
    try:
        vecs = encoder.encode(texts, show_progress_bar=False)
        return vecs.tolist()
    except Exception as e:
        logger.warning(f"Batch embedding failed: {e}")
        return None


def cosine_similarity(a: List[float], b: List[float]) -> float:
    """Compute cosine similarity between two vectors."""
    import math
    dot = sum(x * y for x, y in zip(a, b))
    norm_a = math.sqrt(sum(x * x for x in a))
    norm_b = math.sqrt(sum(x * x for x in b))
    if norm_a == 0 or norm_b == 0:
        return 0.0
    return dot / (norm_a * norm_b)
