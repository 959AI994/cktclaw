"""Task management endpoints."""
import logging

from fastapi import APIRouter, Query

router = APIRouter(prefix="/api/tasks", tags=["tasks"])
logger = logging.getLogger(__name__)


def _get_task_manager():
    from ...harness import get_task_manager
    return get_task_manager()


@router.get("")
async def list_tasks(
    status: str | None = Query(None),
    task_type: str | None = Query(None),
):
    tm = _get_task_manager()
    from . import resolve_async
    try:
        tasks = resolve_async(tm.list_tasks(status=status, task_type=task_type))
        result = []
        for t in tasks:
            if hasattr(t, 'dict'):
                result.append(t.dict())
            elif isinstance(t, dict):
                result.append(t)
            else:
                result.append({
                    "id": getattr(t, 'task_id', '?'),
                    "type": str(getattr(t, 'task_type', '')),
                    "status": str(getattr(t, 'status', '')),
                    "description": getattr(t, 'description', ''),
                })
        return result
    except Exception as e:
        logger.error(f"list_tasks failed: {e}")
        return []


@router.get("/stats")
async def get_stats():
    tm = _get_task_manager()
    from . import resolve_async
    try:
        return resolve_async(tm.get_stats())
    except Exception as e:
        logger.error(f"task_stats failed: {e}")
        return {}


@router.get("/{task_id}")
async def get_task(task_id: str):
    tm = _get_task_manager()
    try:
        task = tm.get_task(task_id)
        if task is None:
            return {"error": "Task not found"}
        if hasattr(task, 'dict'):
            return task.dict()
        return {"id": task_id, "detail": str(task)}
    except Exception as e:
        logger.error(f"get_task failed: {e}")
        return {"error": str(e)}


@router.get("/{task_id}/output")
async def get_task_output(
    task_id: str,
    offset: int | None = Query(None),
    limit: int | None = Query(None),
):
    tm = _get_task_manager()
    try:
        return {"output": tm.read_task_output(task_id, offset=offset, limit=limit)}
    except Exception as e:
        logger.error(f"get_task_output failed: {e}")
        return {"output": "", "error": str(e)}
