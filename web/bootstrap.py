"""
Web runtime bootstrap — ensure ToolRegistry / SkillRegistry are populated
before API handlers serve empty lists.
"""

import asyncio
import concurrent.futures
import logging

from .routers import resolve_async

logger = logging.getLogger(__name__)


def _run_coro(coro):
    """Run a coroutine from sync code (works inside or outside a running loop)."""
    try:
        asyncio.get_running_loop()
    except RuntimeError:
        return asyncio.run(coro)
    with concurrent.futures.ThreadPoolExecutor(max_workers=1) as ex:
        return ex.submit(asyncio.run, coro).result(timeout=120)


def _bootstrap_tools() -> int:
    from ..tools import get_tool_registry
    from ..tools.eda.yosys_tool import YosysTool
    from ..tools.eda.opensta_tool import OpenSTATool
    from ..tools.eda.abc_tool import ABCTool
    from ..tools.eda.openroad_tool import OpenROADTool
    from ..tools.system.bash_tool import BashTool

    registry = get_tool_registry()
    if registry.list_names():
        return len(registry.list_names())

    for tool in (YosysTool(), OpenSTATool(), ABCTool(), OpenROADTool(), BashTool()):
        registry.register(tool, source="builtin")

    try:
        registry.auto_discover_builtin()
    except Exception as e:
        logger.debug(f"auto_discover_builtin: {e}")

    count = len(registry.list_names())
    logger.info(f"Web bootstrap: registered {count} tools")
    return count


def _bootstrap_skills() -> int:
    from ..harness import get_skill_registry

    reg = get_skill_registry()
    stats = resolve_async(reg.get_stats()) or {}
    if stats.get("total_skills", 0) > 0:
        return stats["total_skills"]

    try:
        from .. import config
        from ..skills import (
            register_abc_skill,
            register_yosys_skill,
            register_reverse_skill,
            register_opensta_skill,
            register_ai4eda_skill,
            register_session_memory_skill,
            register_chip_design_skills,
            register_rtl_claw_skills,
            register_fpga_agent_skills,
            register_verilog_generator_skill,
            register_external_skills,
        )
        from ..skills.rltf_skill import register_rltf_skill
        from ..skills.pareto_negotiation_skill import register_pareto_negotiation_skill
        from ..skills.system_loop_skill import register_system_loop_skill

        async def _register_all():
            await register_abc_skill()
            await register_yosys_skill()
            await register_reverse_skill()
            await register_opensta_skill()
            await register_ai4eda_skill()
            await register_session_memory_skill()
            await register_rltf_skill()
            await register_pareto_negotiation_skill()
            await register_chip_design_skills()
            await register_system_loop_skill()
            await register_rtl_claw_skills()
            await register_fpga_agent_skills()
            await register_verilog_generator_skill()
            await register_external_skills(verbose=config.VERBOSE)

        _run_coro(_register_all())
    except Exception as e:
        logger.warning(f"Web bootstrap skills failed: {e}")
        return 0

    stats = resolve_async(reg.get_stats()) or {}
    count = stats.get("total_skills", 0)
    logger.info(f"Web bootstrap: registered {count} skills")
    return count


def _bootstrap_plugins() -> int:
    try:
        from ..plugins import get_plugin_manager

        pm = get_plugin_manager()
        loaded = pm.discover_and_load_all()
        count = len(loaded) if loaded else len(pm.loaded_plugins)
        logger.info(f"Web bootstrap: loaded {count} plugins")
        return count
    except Exception as e:
        logger.debug(f"Web bootstrap plugins: {e}")
        return 0


def ensure_runtime_bootstrapped() -> None:
    """Idempotently ensure tools, skills, and plugins are registered."""
    try:
        _bootstrap_tools()
        _bootstrap_skills()
        _bootstrap_plugins()
    except Exception as e:
        logger.error(f"ensure_runtime_bootstrapped failed: {e}")
