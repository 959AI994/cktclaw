"""
Semantic Search — hybrid retrieval combining keyword + embedding similarity.

Integrates with the existing cktmem ContextManager to provide
semantically relevant context alongside the sliding window.
"""

import logging
from typing import Dict, List, Optional, Tuple

from .vector_store import VectorStore

logger = logging.getLogger(__name__)


class SemanticSearch:
    """
    Hybrid retrieval: keyword matching + semantic similarity.

    Used by ContextManager.build_context() to inject relevant
    memories from previous sessions/turns.
    """

    def __init__(self, store: Optional[VectorStore] = None):
        self._store = store or VectorStore()

    @property
    def store(self) -> VectorStore:
        return self._store

    def index_message(
        self,
        text: str,
        role: str = "assistant",
        session_id: str = "",
        turn_number: int = 0,
    ) -> bool:
        """
        Index a message for future retrieval.

        Only indexes non-trivial messages (assistant responses, tool results).
        Short or empty messages are skipped.
        """
        if not text or len(text.strip()) < 50:
            return False  # Skip trivial messages

        metadata = {
            "role": role,
            "session_id": session_id,
            "turn": turn_number,
        }

        return self._store.add(text[:2000], metadata=metadata)  # Limit text length

    def retrieve_relevant(
        self,
        query: str,
        top_k: int = 5,
        min_score: float = 0.3,
    ) -> List[Dict]:
        """
        Retrieve semantically relevant memories for a query.

        Args:
            query: The user's current question/message.
            top_k: Maximum number of results.
            min_score: Minimum similarity score threshold.

        Returns:
            List of dicts with 'text', 'score', 'metadata'.
        """
        results = self._store.search(query, top_k=top_k)

        relevant = []
        for text, score, metadata in results:
            if score >= min_score:
                relevant.append({
                    "text": text,
                    "score": round(score, 3),
                    "metadata": metadata,
                })

        return relevant

    def format_as_context(self, memories: List[Dict], max_tokens: int = 2000) -> str:
        """
        Format retrieved memories as a context string for the LLM.

        Args:
            memories: Output from retrieve_relevant().
            max_tokens: Approximate token limit (chars / 4).

        Returns:
            Formatted context string, or empty string if no memories.
        """
        if not memories:
            return ""

        parts = ["[Relevant context from previous interactions]"]
        chars_used = len(parts[0])
        char_limit = max_tokens * 4

        for mem in memories:
            text = mem["text"][:500]
            entry = f"\n- (relevance: {mem['score']}) {text}"
            if chars_used + len(entry) > char_limit:
                break
            parts.append(entry)
            chars_used += len(entry)

        return "\n".join(parts)

    @property
    def indexed_count(self) -> int:
        return self._store.size
