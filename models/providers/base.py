"""
BaseLLMProvider - Abstract interface for all LLM providers.

All providers must implement:
- chat_with_context(): Multi-turn conversation with optional tool calling
- analyze(): Verilog code analysis given pre-extracted metrics
"""

from abc import ABC, abstractmethod
from typing import Any, Dict, List, Optional, Union


class BaseLLMProvider(ABC):
    """Abstract base class for LLM communication providers."""

    @abstractmethod
    def chat_with_context(
        self,
        messages: List[Dict[str, str]],
        tools: Optional[List[Dict]] = None,
    ) -> Union[str, Dict[str, Any]]:
        """
        Send a multi-turn conversation to the LLM.

        Args:
            messages: Pre-assembled message list
                      [{"role": "system"/"user"/"assistant", "content": "..."}]
            tools: Optional tool specifications for function calling.

        Returns:
            Either a text response (str) or a tool_call dict:
            {"type": "tool_call", "tool_call_id": str, "name": str, "arguments": dict}
        """
        ...

    @abstractmethod
    def analyze(
        self,
        verilog_code: str,
        metrics: Dict[str, Any],
        system_prompt: str = "",
    ) -> str:
        """
        Analyze Verilog code using the LLM.

        Args:
            verilog_code: The Verilog source code to analyze.
            metrics: Pre-extracted metrics from VerilogMetricsExtractor.
            system_prompt: System prompt to inject.

        Returns:
            Analysis text from the LLM.
        """
        ...
