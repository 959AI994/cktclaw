"""CktClaw Dashboard API routers."""
import asyncio
import concurrent.futures

from fastapi import FastAPI


def resolve_async(v):
    """Resolve a potentially-async value synchronously, working in both sync and async contexts."""
    if not asyncio.iscoroutine(v):
        return v
    try:
        loop = asyncio.get_running_loop()
        with concurrent.futures.ThreadPoolExecutor(max_workers=1) as ex:
            return ex.submit(asyncio.run, v).result(timeout=10)
    except RuntimeError:
        return asyncio.run(v)


def register_routers(app: FastAPI) -> None:
    from . import system, agents, tools, skills, sessions, models, tasks, plugins, memory, config, orchestrator, uploads

    app.include_router(system.router)
    app.include_router(agents.router)
    app.include_router(orchestrator.router)
    app.include_router(uploads.router)
    app.include_router(tools.router)
    app.include_router(skills.router)
    app.include_router(sessions.router)
    app.include_router(models.router)
    app.include_router(tasks.router)
    app.include_router(plugins.router)
    app.include_router(memory.router)
    app.include_router(config.router)
