"""Model provider management + API key configuration."""
import logging
import os

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

router = APIRouter(prefix="/api/models", tags=["models"])
logger = logging.getLogger(__name__)


class SwitchRequest(BaseModel):
    provider: str

class SetModelNameRequest(BaseModel):
    model: str
    provider: str | None = None

class SetKeyRequest(BaseModel):
    provider: str
    api_key: str

class UpdateConfigRequest(BaseModel):
    provider: str
    api_key: str | None = None
    base_url: str | None = None
    model: str | None = None
    temperature: float | None = None
    max_tokens: int | None = None


PROVIDER_META = {
    "deepseek": {"label": "DeepSeek", "env_key": "DEEPSEEK_API_KEY", "default_base": "https://api.deepseek.com", "models": ["deepseek-chat", "deepseek-reasoner"]},
    "claude": {"label": "Anthropic Claude", "env_key": "ANTHROPIC_API_KEY", "default_base": "", "models": ["claude-sonnet-4-6", "claude-opus-4-7", "claude-haiku-4-5"]},
    "openai": {"label": "OpenAI", "env_key": "OPENAI_API_KEY", "default_base": "https://api.openai.com/v1", "models": ["gpt-4o", "gpt-4o-mini", "gpt-4.1"]},
    "local": {"label": "Local (vLLM / Ollama)", "env_key": "CKTCLAW_LOCAL_URL", "default_base": "http://localhost:11434/v1", "models": ["default", "qwen2.5", "llama3", "codellama"]},
}

def _get_router():
    from ...llm import get_model_router
    return get_model_router()

def _get_config():
    from ...config_loader import get_config, save_user_config
    return get_config(), save_user_config

def _save_provider_config(provider: str, updates: dict):
    """Save provider config to ~/.cktclaw/config.yaml and reload the router."""
    cfg, save = _get_config()
    dotted_updates = {}
    for k, v in updates.items():
        if v is not None:
            dotted_updates[f"llm.{provider}.{k}"] = v
    path = save(dotted_updates)
    try:
        _get_router().reload()
    except Exception:
        pass
    return path

def _check_key_status(provider: str) -> dict:
    """Check if a provider has a working API key."""
    meta = PROVIDER_META.get(provider, {})
    env_key = os.environ.get(meta.get("env_key", ""))
    yaml_val = None
    has_yaml = False
    try:
        cfg, _ = _get_config()
        yaml_val = cfg.get(f"llm.{provider}.api_key")
        has_yaml = bool(yaml_val and not str(yaml_val).startswith("#") and str(yaml_val).strip())
    except Exception:
        pass
    has_env = bool(env_key and env_key.strip() and not env_key.startswith("sk-ant-oat"))

    router = _get_router()
    router.initialize()
    is_available = provider in router.available_providers
    is_current = router.current_name == provider
    current_model = router.get_model(provider) if is_available else None

    return {
        "name": provider,
        "label": meta.get("label", provider),
        "has_key": has_env or has_yaml,
        "key_source": "env" if has_env else ("yaml" if has_yaml else "none"),
        "is_available": is_available,
        "is_current": is_current,
        "current_model": current_model or meta.get("models", [None])[0],
        "available_models": meta.get("models", []),
        "default_base_url": meta.get("default_base", ""),
        "base_url": cfg.get(f"llm.{provider}.base_url") if has_yaml else None,
    }


@router.get("")
async def list_models():
    return {
        "current": _get_router().current_name,
        "current_model": _get_router().get_model(),
        "providers": {p: _check_key_status(p) for p in PROVIDER_META},
    }


@router.get("/providers")
async def list_providers():
    return {"providers": {p: _check_key_status(p) for p in PROVIDER_META}}


@router.post("/switch")
async def switch_model(body: SwitchRequest):
    r = _get_router()
    ok = r.switch(body.provider)
    if ok:
        return {"current": r.current_name, "status": "switched"}
    raise HTTPException(status_code=400, detail=f"Provider '{body.provider}' not available. Set its API key first.")


@router.post("/set-key")
async def set_api_key(body: SetKeyRequest):
    provider = body.provider.lower()
    if provider not in PROVIDER_META and provider != "local":
        raise HTTPException(status_code=400, detail=f"Unknown provider: {provider}")

    key = (body.api_key or "").strip()
    if not key:
        raise HTTPException(status_code=400, detail="API key cannot be empty")

    try:
        _save_provider_config(provider, {"api_key": key})
        status = _check_key_status(provider)
        return {"status": "saved", "provider": status}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/update-config")
async def update_provider_config(body: UpdateConfigRequest):
    provider = body.provider.lower()
    if provider not in PROVIDER_META:
        raise HTTPException(status_code=400, detail=f"Unknown provider: {provider}")

    updates = {}
    if body.api_key is not None:
        updates["api_key"] = body.api_key.strip() or None
    if body.base_url is not None:
        updates["base_url"] = body.base_url.strip() or None
    if body.model is not None:
        updates["model"] = body.model.strip() or None
    if body.temperature is not None:
        updates["temperature"] = body.temperature
    if body.max_tokens is not None:
        updates["max_tokens"] = body.max_tokens

    if not updates:
        raise HTTPException(status_code=400, detail="No updates provided")

    try:
        _save_provider_config(provider, updates)
        status = _check_key_status(provider)
        return {"status": "saved", "provider": status}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/reload")
async def reload_models():
    r = _get_router()
    r.reload()
    return {"current": r.current_name, "available": r.available_providers}


@router.post("/set-model")
async def set_model_name(body: SetModelNameRequest):
    r = _get_router()
    ok = r.set_model(body.model, body.provider)
    if ok:
        # persist model preference
        target = body.provider or r.current_name
        _save_provider_config(target, {"model": body.model})
        return {"status": "updated", "model": body.model}
    raise HTTPException(status_code=400, detail="Failed to set model")
