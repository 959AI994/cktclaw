"""System status and health endpoints."""
import asyncio
import time

from fastapi import APIRouter

router = APIRouter(prefix="/api", tags=["system"])

_START_TIME = time.time()


def _resolve(v):
    """If v is a coroutine, run it synchronously in a fresh event loop. Otherwise return as-is."""
    if asyncio.iscoroutine(v):
        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            loop = None
        if loop is None:
            return asyncio.run(v)
        else:
            import concurrent.futures
            with concurrent.futures.ThreadPoolExecutor(max_workers=1) as ex:
                return ex.submit(asyncio.run, v).result(timeout=5)
    return v


@router.get("/status")
async def get_status():
    """Full system snapshot."""
    agents = []
    tools_list = []
    tools_count = 0
    skills_count = 0
    model_info = {}
    task_stats = {}
    harness_stats = {}

    # Agents
    try:
        from ...agents import get_agent_runtime
        runtime = get_agent_runtime()
        agents = _resolve(runtime.list_agents()) if runtime else []
        if not isinstance(agents, list):
            agents = []
    except Exception:
        pass

    # Tools
    try:
        from ...tools import get_tool_registry
        from ..bootstrap import ensure_runtime_bootstrapped

        ensure_runtime_bootstrapped()
        tool_reg = get_tool_registry()
        if tool_reg:
            names = _resolve(tool_reg.list_names())
            if isinstance(names, list):
                tools_list = names
                tools_count = len(tools_list)
    except Exception:
        pass

    # Skills
    try:
        from ...harness import get_skill_registry
        from ..bootstrap import ensure_runtime_bootstrapped

        ensure_runtime_bootstrapped()
        skill_reg = get_skill_registry()
        if skill_reg:
            stats = _resolve(skill_reg.get_stats())
            if isinstance(stats, dict):
                skills_count = stats.get("total_skills", stats.get("total", 0))
    except Exception:
        pass

    # Model
    try:
        from ...llm import get_model_router
        router = get_model_router()
        if router:
            router.initialize()
            model_info = {
                "current": router.current_name or "none",
                "available": router.available_providers or [],
                "model": router.get_model() or "",
            }
    except Exception:
        pass

    # Tasks
    try:
        from ...harness import get_task_manager
        tm = get_task_manager()
        if tm:
            task_stats = _resolve(tm.get_stats())
            if not isinstance(task_stats, dict):
                task_stats = {}
    except Exception:
        pass

    # Harness
    try:
        from ...harness.bootstrap.state import get_state_manager
        sm = get_state_manager()
        harness_stats = _resolve(sm.get_stats())
        if not isinstance(harness_stats, dict):
            harness_stats = {}
    except Exception:
        pass

    # CktMem sessions
    sessions_info = {"latest_id": None, "count": 0}
    try:
        from ..deps import get_web_storage
        storage = get_web_storage()
        session_list = _resolve(storage.list_sessions(limit=50)) or []
        sessions_info["count"] = len(session_list)
        if session_list:
            sessions_info["latest_id"] = session_list[0].get("session_id")
    except Exception:
        pass

    uptime = time.time() - _START_TIME

    return {
        "status": "ok",
        "uptime_seconds": round(uptime, 1),
        "agents": agents,
        "model": model_info,
        "tools": {"count": tools_count, "names": tools_list},
        "skills": {"count": skills_count},
        "tasks": task_stats,
        "harness": harness_stats,
        "sessions": sessions_info,
    }


@router.get("/health")
async def health():
    return {"status": "ok"}
