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

        # DeepSeek (default)
        deepseek_key = (
            os.environ.get("CKTCLAW_DEEPSEEK_KEY")
            or os.environ.get("DEEPSEEK_API_KEY", "")
        )
        if deepseek_key:
            self._providers["deepseek"] = DeepSeekProvider(
                api_key=deepseek_key,
                base_url=os.environ.get("DEEPSEEK_BASE_URL", "https://api.deepseek.com"),
                model=os.environ.get("DEEPSEEK_MODEL", "deepseek-chat"),
            )

        # OpenAI-compatible
        openai_key = (
            os.environ.get("CKTCLAW_OPENAI_KEY")
            or os.environ.get("OPENAI_API_KEY", "")
        )
        if openai_key:
            self._providers["openai"] = OpenAICompatProvider(
                api_key=openai_key,
                base_url=os.environ.get("OPENAI_BASE_URL", "https://api.openai.com/v1"),
                model=os.environ.get("OPENAI_MODEL", "gpt-4o"),
            )

        # Claude
        claude_key = (
            os.environ.get("CKTCLAW_CLAUDE_KEY")
            or os.environ.get("ANTHROPIC_API_KEY", "")
        )
        if claude_key:
            self._providers["claude"] = AnthropicProvider(
                api_key=claude_key,
                model=os.environ.get("ANTHROPIC_MODEL", "claude-sonnet-4-20250514"),
            )

        # Local / custom OpenAI-compatible (vLLM, Ollama, etc.)
        local_url = os.environ.get("CKTCLAW_LOCAL_URL")
        if local_url:
            self._providers["local"] = OpenAICompatProvider(
                api_key=os.environ.get("CKTCLAW_LOCAL_KEY", "none"),
                base_url=local_url,
                model=os.environ.get("CKTCLAW_LOCAL_MODEL", "default"),
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
