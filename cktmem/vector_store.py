"""
Vector Store — lightweight file-backed vector storage for semantic memory.

Uses numpy for fast similarity search when available, falls back to
pure Python. Stores vectors + metadata as JSON files in .cktclaw/vectors/.
"""

import json
import logging
import os
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from .embeddings import cosine_similarity, embed_text, get_embedding_model_id

logger = logging.getLogger(__name__)


class VectorEntry:
    """A single vector entry with metadata."""

    def __init__(
        self,
        text: str,
        vector: List[float],
        metadata: Optional[Dict[str, Any]] = None,
        entry_id: str = "",
    ):
        self.text = text
        self.vector = vector
        self.metadata = metadata or {}
        self.entry_id = entry_id or self._generate_id()

    def _generate_id(self) -> str:
        import hashlib
        return hashlib.md5(self.text[:200].encode()).hexdigest()[:12]

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.entry_id,
            "text": self.text,
            "vector": self.vector,
            "metadata": self.metadata,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "VectorEntry":
        return cls(
            text=data["text"],
            vector=data["vector"],
            metadata=data.get("metadata", {}),
            entry_id=data.get("id", ""),
        )


class VectorStore:
    """
    Simple file-backed vector store for semantic memory.

    Stores embeddings in .cktclaw/vectors/<project>.json.
    Supports add, search (cosine similarity), and persistence.
    """

    def __init__(self, store_path: Optional[str] = None, max_entries: int = 1000):
        self._entries: List[VectorEntry] = []
        self._max_entries = max_entries
        self._model_id: str = ""

        if store_path:
            self._store_path = Path(store_path)
        else:
            self._store_path = Path.cwd() / ".cktclaw" / "vectors" / "memory.json"

        self._load()

    def _load(self) -> None:
        """Load vectors from disk."""
        if self._store_path.is_file():
            try:
                data = json.loads(self._store_path.read_text())
                self._model_id = data.get("model_id", "")
                self._entries = [VectorEntry.from_dict(d) for d in data.get("entries", [])]
                current = get_embedding_model_id()
                if self._model_id and current and self._model_id != current:
                    logger.warning(
                        "Vector store model %s != current %s; ignoring stored vectors",
                        self._model_id,
                        current,
                    )
                    self._entries = []
                logger.debug(f"Loaded {len(self._entries)} vectors from {self._store_path}")
            except Exception as e:
                logger.warning(f"Failed to load vector store: {e}")
                self._entries = []
                self._model_id = ""

    def _save(self) -> None:
        """Persist vectors to disk."""
        try:
            self._store_path.parent.mkdir(parents=True, exist_ok=True)
            data = {
                "model_id": self._model_id or get_embedding_model_id(),
                "entries": [e.to_dict() for e in self._entries],
            }
            self._store_path.write_text(json.dumps(data, ensure_ascii=False))
        except Exception as e:
            logger.warning(f"Failed to save vector store: {e}")

    def _ensure_model(self) -> None:
        current = get_embedding_model_id()
        if self._model_id and self._model_id != current:
            logger.warning(
                "Embedding model changed (%s -> %s); clearing vector store",
                self._model_id,
                current,
            )
            self._entries = []
        self._model_id = current

    def add(self, text: str, metadata: Optional[Dict[str, Any]] = None) -> bool:
        """
        Add a text entry to the store (auto-embeds).

        Returns True if embedding succeeded, False if not available.
        """
        self._ensure_model()
        vector = embed_text(text, task="retrieval.passage")
        if vector is None:
            return False

        entry = VectorEntry(text=text, vector=vector, metadata=metadata)

        # Deduplicate by ID
        existing_ids = {e.entry_id for e in self._entries}
        if entry.entry_id in existing_ids:
            return True  # Already exists

        self._entries.append(entry)

        # Trim to max size (remove oldest)
        if len(self._entries) > self._max_entries:
            self._entries = self._entries[-self._max_entries:]

        self._save()
        return True

    def search(self, query: str, top_k: int = 5) -> List[Tuple[str, float, Dict]]:
        """
        Search for similar entries by cosine similarity.

        Returns list of (text, score, metadata) tuples sorted by score descending.
        """
        if not self._entries:
            return []

        query_vec = embed_text(query, task="retrieval.query")
        if query_vec is None:
            return []

        scored = []
        for entry in self._entries:
            score = cosine_similarity(query_vec, entry.vector)
            scored.append((entry.text, score, entry.metadata))

        scored.sort(key=lambda x: x[1], reverse=True)
        return scored[:top_k]

    def list_entries(self, limit: int = 100) -> List[Dict[str, Any]]:
        """Return entry summaries without full embedding vectors."""
        capped = limit if limit > 0 else len(self._entries)
        return [
            {
                "id": e.entry_id,
                "text": e.text,
                "metadata": e.metadata,
            }
            for e in self._entries[-capped:]
        ]

    def clear(self) -> None:
        """Remove all entries."""
        self._entries = []
        self._save()

    @property
    def size(self) -> int:
        return len(self._entries)
