"""
Model Router — selects and manages LLM providers.
"""

import logging
import os
from typing import Dict, List, Optional

from .base import AsyncLLMProvider
from .deepseek import DeepSeekProvider
from .openai_compat import OpenAICompatProvider
from .anthropic_provider import AnthropicProvider

logger = logging.getLogger(__name__)


class ModelRouter:
    """
    Routes LLM requests to the appropriate provider.

    Manages provider instantiation and runtime switching via /model command.
    """

    def __init__(self):
        self._providers: Dict[str, AsyncLLMProvider] = {}
        self._current_provider_name: str = "deepseek"
        self._initialized = False

    def initialize(self) -> None:
        """Initialize available providers from environment configuration."""
        if self._initialized:
            return

        # Resolve credentials via the shared loader (env -> ~/.cktclaw/config.yaml),
        # so keys persist across shells without re-sourcing .env each session.
        from ..api_credentials import (
            get_anthropic_api_key,
            get_deepseek_api_key,
            get_openai_api_key,
        )

        def _cfg(dotted: str, default=None):
            """Read a value from ~/.cktclaw/config.yaml (best-effort)."""
            try:
                from ..config_loader import get_config
                val = get_config().get(dotted)
                return val if val not in (None, "") else default
            except Exception:
                return default

        # DeepSeek (default)
        deepseek_key = get_deepseek_api_key(required=False) or ""
        if deepseek_key:
            self._providers["deepseek"] = DeepSeekProvider(
                api_key=deepseek_key,
                base_url=os.environ.get("DEEPSEEK_BASE_URL")
                or _cfg("llm.deepseek.base_url", "https://api.deepseek.com"),
                model=os.environ.get("DEEPSEEK_MODEL")
                or _cfg("llm.deepseek.model", "deepseek-chat"),
            )

        # OpenAI-compatible
        openai_key = get_openai_api_key(required=False) or ""
        if openai_key:
            self._providers["openai"] = OpenAICompatProvider(
                api_key=openai_key,
                base_url=os.environ.get("OPENAI_BASE_URL")
                or _cfg("llm.openai.base_url", "https://api.openai.com/v1"),
                model=os.environ.get("OPENAI_MODEL")
                or _cfg("llm.openai.model", "gpt-4o"),
            )

        # Claude — requires the `anthropic` SDK. Skip (with a clear hint) when the
        # key is set but the package is missing, so we never select a provider
        # that cannot actually run.
        claude_key = get_anthropic_api_key(required=False) or ""
        if claude_key and claude_key.startswith("sk-ant-oat"):
            # Claude Code OAuth subscription token (sk-ant-oat...) — usable only by
            # the Claude Code CLI, not the standard Messages API. Skip silently at
            # startup; /model shows a clear message if the user picks Claude.
            logger.debug(
                "ANTHROPIC_API_KEY looks like a Claude Code OAuth token "
                "(sk-ant-oat...); skipping the claude provider."
            )
        elif claude_key:
            try:
                import anthropic  # noqa: F401
                self._providers["claude"] = AnthropicProvider(
                    api_key=claude_key,
                    model=os.environ.get("ANTHROPIC_MODEL")
                    or _cfg("llm.claude.model", "claude-sonnet-4-6"),
                )
            except ImportError:
                logger.warning(
                    "ANTHROPIC_API_KEY is set but the 'anthropic' package is not "
                    "installed; skipping the claude provider. Run: pip install anthropic"
                )

        # Local / custom OpenAI-compatible (vLLM, Ollama, LM Studio, etc.)
        local_url = os.environ.get("CKTCLAW_LOCAL_URL") or _cfg("llm.local.base_url")
        if local_url:
            self._providers["local"] = OpenAICompatProvider(
                api_key=os.environ.get("CKTCLAW_LOCAL_KEY")
                or _cfg("llm.local.api_key", "none"),
                base_url=local_url,
                model=os.environ.get("CKTCLAW_LOCAL_MODEL")
                or _cfg("llm.local.model", "default"),
            )

        self._initialized = True

        # Select default
        if self._current_provider_name not in self._providers:
            if self._providers:
                self._current_provider_name = next(iter(self._providers))
            else:
                logger.warning("No LLM providers configured!")

    @property
    def current_provider(self) -> Optional[AsyncLLMProvider]:
        """Get the currently active provider."""
        self.initialize()
        return self._providers.get(self._current_provider_name)

    @property
    def current_name(self) -> str:
        """Name of the current provider."""
        return self._current_provider_name

    def switch(self, provider_name: str) -> bool:
        """
        Switch to a different provider.

        Args:
            provider_name: Name of the provider to switch to.

        Returns:
            True if switch was successful.
        """
        self.initialize()

        # Handle aliases
        aliases = {
            "ds": "deepseek",
            "gpt": "openai",
            "gpt4": "openai",
            "gpt-4o": "openai",
            "anthropic": "claude",
            "sonnet": "claude",
            "opus": "claude",
            "ollama": "local",
            "vllm": "local",
            "qwen": "local",
        }
        resolved = aliases.get(provider_name.lower(), provider_name.lower())

        if resolved not in self._providers:
            logger.warning(f"Provider '{resolved}' not available. Available: {self.available_providers}")
            return False

        self._current_provider_name = resolved
        logger.info(f"Switched to LLM provider: {resolved}")
        return True

    def reload(self) -> None:
        """
        Re-initialize providers from current credentials/config.

        Used after the user adds or changes an API key at runtime (via /model),
        so newly-configured providers become available without restarting.
        The current selection is preserved when still available.
        """
        previous = self._current_provider_name
        self._providers = {}
        self._initialized = False
        self.initialize()
        if previous in self._providers:
            self._current_provider_name = previous

    def set_model(self, model: str, provider_name: Optional[str] = None) -> bool:
        """Set the model string on a provider (defaults to the current one)."""
        self.initialize()
        name = provider_name or self._current_provider_name
        provider = self._providers.get(name)
        if provider is None:
            return False
        setattr(provider, "model", model)
        logger.info(f"Set model for provider '{name}' -> {model}")
        return True

    def get_model(self, provider_name: Optional[str] = None) -> Optional[str]:
        """Get the current model string of a provider."""
        self.initialize()
        name = provider_name or self._current_provider_name
        provider = self._providers.get(name)
        return getattr(provider, "model", None) if provider else None

    @property
    def available_providers(self) -> List[str]:
        """List of configured provider names."""
        self.initialize()
        return list(self._providers.keys())

    def get_provider(self, name: str) -> Optional[AsyncLLMProvider]:
        """Get a specific provider by name."""
        self.initialize()
        return self._providers.get(name)

    def register_provider(self, name: str, provider: AsyncLLMProvider) -> None:
        """Register a custom provider."""
        self._providers[name] = provider

    def summary(self) -> str:
        """Human-readable summary of available providers."""
        self.initialize()
        lines = [f"Current: {self._current_provider_name}"]
        for name, provider in self._providers.items():
            marker = " ←" if name == self._current_provider_name else ""
            lines.append(f"  {name}: {provider.provider_name}{marker}")
        return "\n".join(lines)


# Global singleton
_model_router: Optional[ModelRouter] = None


def get_model_router() -> ModelRouter:
    """Get or create the global ModelRouter."""
    global _model_router
    if _model_router is None:
        _model_router = ModelRouter()
    return _model_router
