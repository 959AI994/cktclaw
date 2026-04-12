"""
LLM Provider abstractions for CktClaw.

Provides a unified interface for different LLM backends:
- DeepSeekProvider: Cloud API via DeepSeek
- LocalCodeVProvider: Local GPU-based CodeV model
"""

from .base import BaseLLMProvider
from .deepseek_provider import DeepSeekProvider
from .local_codev_provider import LocalCodeVProvider

__all__ = [
    "BaseLLMProvider",
    "DeepSeekProvider",
    "LocalCodeVProvider",
]
