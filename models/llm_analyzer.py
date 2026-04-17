"""
LLMVerilogAnalyzer - Thin facade for LLM-based Verilog analysis.

Delegates all operations to provider implementations:
- DeepSeekProvider: Cloud API via DeepSeek
- LocalCodeVProvider: Local GPU-based CodeV model

Maintains backward compatibility with existing handler code.
"""

import re
from typing import Any, Dict, List, Optional, Union

from .providers.base import BaseLLMProvider
from .providers.deepseek_provider import DeepSeekProvider
from .providers.local_codev_provider import LocalCodeVProvider
from ..utils.verilog_parser import VerilogMetricsExtractor
from ..utils.tool_call_parser import ToolCallParser

try:
    from ..config import LOGICRT_SYSTEM_PROMPT, QWEN_MODEL_PATH, QWEN_GPU_ID
except ImportError:
    LOGICRT_SYSTEM_PROMPT = ""
    QWEN_MODEL_PATH = "models/qwen/Qwen2.5-3B"
    QWEN_GPU_ID = -2


class LLMVerilogAnalyzer:
    """
    Facade for LLM-based Verilog analysis with dual-engine support.

    Routes requests to the appropriate provider based on model_choice:
    - "deepseek" → DeepSeekProvider (cloud API)
    - "local"    → LocalCodeVProvider (GPU-based)

    Backward-compatible: same constructor and method signatures as before.
    """

    # Kept as class attribute for backward compatibility (main.py reads this)
    LOGICRT_SYSTEM_PROMPT = LOGICRT_SYSTEM_PROMPT

    def __init__(
        self,
        codev_path: str = "models/llm_decoder/CodeV",
        gpu_id: int = -2,
        verbose: bool = True,
    ):
        self.verbose = verbose
        self.deepseek_provider = DeepSeekProvider(verbose=verbose)
        self.local_provider = LocalCodeVProvider(
            codev_path=codev_path, gpu_id=gpu_id, verbose=verbose
        )
        self.qwen_provider = LocalCodeVProvider(
            codev_path=QWEN_MODEL_PATH, gpu_id=QWEN_GPU_ID, verbose=verbose
        )
        self._tool_parser = ToolCallParser(verbose=verbose)

        if verbose:
            print("  [LLMVerilogAnalyzer] Initialized (multi-engine mode)")
            print("    → DeepSeek API: ready")
            print(f"    → Local CodeV : lazy-load from '{codev_path}'")
            print(f"    → Local Qwen  : lazy-load from '{QWEN_MODEL_PATH}'")

    # ── Provider routing ──

    def _get_provider(self, model_choice: str) -> BaseLLMProvider:
        if model_choice == "local":
            return self.local_provider
        elif model_choice == "qwen":
            return self.qwen_provider
        else:
            return self.deepseek_provider

    # ── Public API (backward-compatible) ──

    def analyze(self, verilog_code: str, model_choice: str = "deepseek") -> Dict[str, Any]:
        """Analyze Verilog code and generate a detailed report."""
        if not verilog_code or len(verilog_code.strip()) == 0:
            return {
                "status": "error",
                "message": "Empty Verilog code",
                "metrics": {},
                "description": "No code to analyze",
            }

        metrics = VerilogMetricsExtractor.extract_metrics(verilog_code)
        provider = self._get_provider(model_choice)
        description = provider.analyze(
            verilog_code, metrics, system_prompt=self.LOGICRT_SYSTEM_PROMPT
        )

        # Clean markdown
        description = re.sub(r'\n{3,}', '\n\n', description)
        lines = [line.rstrip() for line in description.split('\n')]
        description = '\n'.join(lines).strip()

        return {
            "status": "success",
            "metrics": metrics,
            "description": description,
            "code_preview": verilog_code[:500] + "..." if len(verilog_code) > 500 else verilog_code,
        }

    def chat(
        self,
        history: List[Dict[str, str]],
        user_message: str,
        model_choice: str = "deepseek",
    ) -> Union[str, Dict[str, Any]]:
        """Legacy multi-turn chat interface (backward-compatible)."""
        messages = [{"role": "system", "content": self.LOGICRT_SYSTEM_PROMPT}]
        for msg in history:
            messages.append({"role": msg["role"], "content": msg["content"]})
        messages.append({"role": "user", "content": user_message})
        return self.chat_with_context(messages, model_choice)

    def chat_with_context(
        self,
        messages: List[Dict[str, str]],
        model_choice: str = "deepseek",
        tools: Optional[List[Dict]] = None,
    ) -> Union[str, Dict[str, Any]]:
        """Multi-turn chat with pre-assembled messages."""
        provider = self._get_provider(model_choice)
        return provider.chat_with_context(messages, tools=tools)

    def summarize_after_tool(
        self,
        messages: List[Dict[str, str]],
        tool_call_id: str,
        tool_name: str,
        tool_args: Dict[str, Any],
        tool_output: str,
        model_choice: str = "deepseek",
    ) -> Union[str, Dict[str, Any]]:
        """Ask the model to summarize tool execution results."""
        provider = self._get_provider(model_choice)
        return provider.summarize_after_tool(
            messages, tool_call_id, tool_name, tool_args, tool_output
        )

    def _extract_local_tool_call(self, text: str) -> Optional[Dict[str, Any]]:
        """Backward-compatible wrapper for ToolCallParser.parse()."""
        return self._tool_parser.parse(text)
