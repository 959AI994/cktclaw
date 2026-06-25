"""Configuration endpoints."""
import logging

from fastapi import APIRouter, HTTPException, Request

router = APIRouter(prefix="/api/config", tags=["config"])
logger = logging.getLogger(__name__)


def _get_config():
    from ...config_loader import get_config
    return get_config()


def _save_config(updates: dict):
    from ...config_loader import save_user_config
    return save_user_config(updates)


@router.get("")
async def get_full_config():
    try:
        cfg = _get_config()
        return cfg.to_dict() if hasattr(cfg, 'to_dict') else {"data": str(cfg)}
    except Exception as e:
        logger.error(f"get_config failed: {e}")
        return {"error": str(e)}


@router.get("/{path:path}")
async def get_config_value(path: str):
    try:
        cfg = _get_config()
        val = cfg.get(path)
        return {"path": path, "value": val}
    except Exception as e:
        logger.error(f"get_config_value failed: {e}")
        return {"path": path, "value": None, "error": str(e)}


@router.put("")
async def update_config(request: Request):
    try:
        body = await request.json()
        path = _save_config(body)
        return {"status": "saved", "path": str(path) if path else None}
    except Exception as e:
        logger.error(f"update_config failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))
