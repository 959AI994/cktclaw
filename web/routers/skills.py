"""Skill registry endpoints."""
import asyncio
import logging

from fastapi import APIRouter, HTTPException

router = APIRouter(prefix="/api/skills", tags=["skills"])
logger = logging.getLogger(__name__)


def _get_skill_registry():
    from ...harness import get_skill_registry
    return get_skill_registry()


def _resolve(v):
    if not asyncio.iscoroutine(v):
        return v
    try:
        loop = asyncio.get_running_loop()
        import concurrent.futures
        with concurrent.futures.ThreadPoolExecutor(max_workers=1) as ex:
            return ex.submit(asyncio.run, v).result(timeout=5)
    except RuntimeError:
        return asyncio.run(v)


def _normalize_stats(stats: dict) -> dict:
    if not stats:
        return {"total": 0, "total_skills": 0, "by_type": {}, "by_source": {}, "total_aliases": 0}
    total = stats.get("total_skills", stats.get("total", 0))
    return {
        "total": total,
        "total_skills": total,
        "conditional_skills": stats.get("conditional_skills", 0),
        "activated_skills": stats.get("activated_skills", 0),
        "total_aliases": stats.get("total_aliases", 0),
        "by_type": stats.get("by_type", {}),
        "by_source": stats.get("by_source", {}),
        "total_tokens": stats.get("total_tokens", 0),
    }


def _skill_to_dict(s) -> dict:
    loaded_from = str(getattr(s, "loaded_from", ""))
    if loaded_from.startswith("LoadedFrom."):
        loaded_from = loaded_from.split(".", 1)[-1]
    skill_type = str(getattr(s, "skill_type", ""))
    if skill_type.startswith("SkillType."):
        skill_type = skill_type.split(".", 1)[-1]
    return {
        "name": getattr(s, "name", "?"),
        "display_name": getattr(s, "display_name", ""),
        "description": getattr(s, "description", ""),
        "skill_type": skill_type,
        "aliases": getattr(s, "aliases", []) or [],
        "loaded_from": loaded_from,
        "user_invocable": getattr(s, "user_invocable", True),
        "is_hidden": getattr(s, "is_hidden", False),
        "version": getattr(s, "version", ""),
    }


@router.get("")
async def list_skills(user_invocable_only: bool = False):
    from ..bootstrap import ensure_runtime_bootstrapped

    ensure_runtime_bootstrapped()
    reg = _get_skill_registry()
    if reg is None:
        return []
    try:
        skills = _resolve(reg.list_skills(user_invocable_only=user_invocable_only))
        result = []
        if not skills:
            return []
        for s in skills if hasattr(skills, "__iter__") else []:
            try:
                result.append(_skill_to_dict(s))
            except Exception:
                pass
        return result
    except Exception as e:
        logger.error(f"list_skills failed: {e}")
        return []


@router.get("/stats")
async def get_stats():
    from ..bootstrap import ensure_runtime_bootstrapped

    ensure_runtime_bootstrapped()
    reg = _get_skill_registry()
    if reg is None:
        return _normalize_stats({})
    try:
        return _normalize_stats(_resolve(reg.get_stats()) or {})
    except Exception as e:
        logger.error(f"get_stats failed: {e}")
        return _normalize_stats({})


@router.get("/{name}")
async def get_skill(name: str):
    from ..bootstrap import ensure_runtime_bootstrapped

    ensure_runtime_bootstrapped()
    reg = _get_skill_registry()
    if reg is None:
        raise HTTPException(status_code=404, detail=f"Skill '{name}' not found")
    try:
        skill = _resolve(reg.get_skill(name))
        if skill is None:
            raise HTTPException(status_code=404, detail=f"Skill '{name}' not found")
        d = _skill_to_dict(skill)
        d.update({
            "when_to_use": getattr(skill, "when_to_use", ""),
            "execution_context": str(getattr(skill, "execution_context", "")),
            "allowed_tools": getattr(skill, "allowed_tools", []) or [],
            "argument_hint": getattr(skill, "argument_hint", ""),
        })
        return d
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"get_skill failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))
