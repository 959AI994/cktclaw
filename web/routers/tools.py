"""Tool registry endpoints."""
import logging

from fastapi import APIRouter

router = APIRouter(prefix="/api/tools", tags=["tools"])
logger = logging.getLogger(__name__)


def _get_tool_registry():
    from ...tools import get_tool_registry
    return get_tool_registry()


def _tool_to_dict(t, source: str = "builtin") -> dict:
    return {
        "name": getattr(t, "name", "?"),
        "description": getattr(t, "description", ""),
        "category": getattr(t, "category", "general"),
        "read_only": getattr(t, "read_only", False),
        "source": source,
        "parameters": getattr(t, "parameters", {}) or {},
        "requires": getattr(t, "requires", []) or [],
    }


@router.get("")
async def list_tools():
    from ..bootstrap import ensure_runtime_bootstrapped

    ensure_runtime_bootstrapped()
    reg = _get_tool_registry()
    try:
        tools = reg.list_tools()
        result = []
        for t in tools:
            if hasattr(t, "name"):
                src = reg.get_source(getattr(t, "name", "")) or "builtin"
                result.append(_tool_to_dict(t, source=src))
        return result
    except Exception as e:
        logger.error(f"list_tools failed: {e}")
        return []


@router.get("/categories")
async def list_categories():
    from ..bootstrap import ensure_runtime_bootstrapped

    ensure_runtime_bootstrapped()
    reg = _get_tool_registry()
    try:
        categories: dict = {}
        for t in reg.list_tools():
            cat = getattr(t, "category", "general")
            categories.setdefault(cat, []).append(getattr(t, "name", "?"))
        return categories
    except Exception as e:
        logger.error(f"list_categories failed: {e}")
        return {}
