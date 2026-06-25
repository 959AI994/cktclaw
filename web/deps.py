"""Shared web-layer dependencies (Storage, ContextManager)."""

from typing import Optional

_context_manager: Optional[object] = None


def get_web_storage():
    from .. import config
    from ..cktmem import Storage

    return Storage(config.CLI_DATABASE_PATH)


def get_web_context_manager():
    global _context_manager
    if _context_manager is None:
        from .. import config
        from ..cktmem import ContextManager
        from ..cktmem.models import CompactConfig

        _context_manager = ContextManager(
            storage=get_web_storage(),
            system_prompt=config.LOGICRT_SYSTEM_PROMPT,
            config=CompactConfig(
                auto_compact_threshold=150_000,
                target_tokens=40_000,
                buffer_tokens=13_000,
            ),
        )
    return _context_manager
