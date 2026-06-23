"""Plugin management endpoints."""
import logging

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

router = APIRouter(prefix="/api/plugins", tags=["plugins"])
logger = logging.getLogger(__name__)


class InstallRequest(BaseModel):
    source_path: str | None = None
    git_url: str | None = None


def _get_plugin_manager():
    from ...plugins import get_plugin_manager
    return get_plugin_manager()


def _emit(event_type: str, data: dict):
    try:
        from ..server import emit_event
        emit_event(event_type, data)
    except Exception:
        pass


@router.get("")
async def list_plugins():
    from ..bootstrap import ensure_runtime_bootstrapped

    ensure_runtime_bootstrapped()
    pm = _get_plugin_manager()
    try:
        pm.discover_and_load_all()
        plugins = []
        for p in pm.loaded_plugins.values() if hasattr(pm, 'loaded_plugins') else []:
            plugins.append({
                "name": getattr(p, 'name', '?'),
                "version": getattr(p, 'version', ''),
                "description": getattr(p, 'description', ''),
                "author": getattr(p, 'author', ''),
                "status": str(getattr(p, 'status', 'unknown')),
                "error_message": getattr(p, 'error_message', ''),
            })
        return plugins
    except Exception as e:
        logger.error(f"list_plugins failed: {e}")
        return []


@router.post("/install")
async def install_plugin(body: InstallRequest):
    pm = _get_plugin_manager()
    if body.git_url:
        try:
            info = pm.install_from_git(body.git_url)
        except AttributeError:
            raise HTTPException(status_code=501, detail="Git install not available")
    elif body.source_path:
        try:
            info = pm.install_from_path(body.source_path)
        except AttributeError:
            raise HTTPException(status_code=501, detail="Path install not available")
    else:
        raise HTTPException(status_code=400, detail="Provide source_path or git_url")

    if info:
        _emit("plugin:installed", {"name": getattr(info, 'name', '?')})
        return {"status": "installed", "name": getattr(info, 'name', '?')}
    raise HTTPException(status_code=500, detail="Install failed")


@router.post("/{name}/uninstall")
async def uninstall_plugin(name: str):
    pm = _get_plugin_manager()
    try:
        ok = pm.uninstall(name)
        if ok:
            _emit("plugin:uninstalled", {"name": name})
            return {"status": "uninstalled"}
        raise HTTPException(status_code=404, detail=f"Plugin '{name}' not found")
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"uninstall_plugin failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/reload")
async def reload_plugins():
    pm = _get_plugin_manager()
    try:
        results = pm.discover_and_load_all()
        return {"status": "reloaded", "count": len(results) if results else 0}
    except Exception as e:
        logger.error(f"reload_plugins failed: {e}")
        return {"error": str(e)}
