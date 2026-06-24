"""Shared helpers for indexing assistant turns into semantic memory."""

import logging
from typing import Any, Optional

logger = logging.getLogger(__name__)


def index_assistant_turn(
    semantic_search: Any,
    session_id: str,
    content: str,
) -> bool:
    """
    Index an assistant reply for future semantic retrieval.

    Skips trivial/short messages. Never raises.
    """
    if not content or len(content.strip()) < 50:
        return False
    if semantic_search is None:
        return False
    try:
        return bool(
            semantic_search.index_message(
                content,
                role="assistant",
                session_id=session_id,
            )
        )
    except Exception as e:
        logger.debug("Semantic index failed: %s", e)
        return False
