"""
API Credentials Loader — secure resolution of provider API keys.

Priority: CKTCLAW_<PROVIDER>_KEY env > <PROVIDER>_API_KEY env > ~/.cktclaw/config.yaml > error

NEVER hardcode keys here. NEVER import DEEPSEEK_CONFIG["api_key"] here.
"""
import logging
import os
from typing import Optional

logger = logging.getLogger(__name__)


class CredentialError(RuntimeError):
    """Raised when a required API credential cannot be resolved."""


def _resolve_from_yaml(provider: str) -> Optional[str]:
    try:
        from .config_loader import get_config
        cfg = get_config()
        val = cfg.get(f"llm.{provider}.api_key")
        if val and isinstance(val, str) and val.strip() and not val.startswith("#"):
            return val.strip()
    except Exception:
        pass
    return None


def get_deepseek_api_key(required: bool = True) -> Optional[str]:
    key = (
        os.environ.get("CKTCLAW_DEEPSEEK_KEY")
        or os.environ.get("DEEPSEEK_API_KEY")
        or _resolve_from_yaml("deepseek")
    )
    if key:
        return key
    if required:
        raise CredentialError(
            "DeepSeek API key not found. Provide it via:\n"
            "  export DEEPSEEK_API_KEY=sk-...\n"
            "  or set llm.deepseek.api_key in ~/.cktclaw/config.yaml"
        )
    return None


def get_anthropic_api_key(required: bool = False) -> Optional[str]:
    key = (
        os.environ.get("CKTCLAW_CLAUDE_KEY")
        or os.environ.get("ANTHROPIC_API_KEY")
        or _resolve_from_yaml("claude")
    )
    if key:
        return key
    if required:
        raise CredentialError(
            "Anthropic API key not found. Set ANTHROPIC_API_KEY or "
            "llm.claude.api_key in ~/.cktclaw/config.yaml"
        )
    return None


def get_openai_api_key(required: bool = False) -> Optional[str]:
    key = (
        os.environ.get("CKTCLAW_OPENAI_KEY")
        or os.environ.get("OPENAI_API_KEY")
        or _resolve_from_yaml("openai")
    )
    if key:
        return key
    if required:
        raise CredentialError(
            "OpenAI API key not found. Set OPENAI_API_KEY or "
            "llm.openai.api_key in ~/.cktclaw/config.yaml"
        )
    return None
