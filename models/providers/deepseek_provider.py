"""
DeepSeekProvider - Cloud LLM provider via DeepSeek API.

Handles HTTP communication, authentication, tool call parsing from
native API responses, and fallback text extraction.
"""

import json
import re
import requests
from typing import Any, Dict, List, Optional, Union

from .base import BaseLLMProvider
from ...utils.tool_call_parser import ToolCallParser
from ...utils.verilog_parser import VerilogMetricsExtractor

try:
    from ...config import DEEPSEEK_CONFIG
except ImportError:
    DEEPSEEK_CONFIG = {
        "base_url": "https://api.deepseek.com",
        "default_model": "deepseek-chat",
        "timeout": 120,
        "temperature": 0.3,
        "max_tokens": 2000,
    }

try:
    from ...api_credentials import get_deepseek_api_key as _get_api_key, CredentialError
except ImportError:
    def _get_api_key(required=False):
        import os
        return os.environ.get("CKTCLAW_DEEPSEEK_KEY") or os.environ.get("DEEPSEEK_API_KEY", "")

    class CredentialError(RuntimeError):
        pass


class DeepSeekProvider(BaseLLMProvider):
    """DeepSeek API-based LLM provider."""

    def __init__(self, verbose: bool = False):
        self.verbose = verbose
        self._tool_parser = ToolCallParser(verbose=verbose)
        try:
            self._api_key: str = _get_api_key(required=False) or ""
        except CredentialError:
            self._api_key = ""

    def _log(self, msg: str) -> None:
        if self.verbose:
            print(msg)

    @staticmethod
    def _clean_markdown(text: str) -> str:
        """Clean up markdown text: collapse excess newlines, strip trailing spaces."""
        text = re.sub(r'\n{3,}', '\n\n', text)
        lines = [line.rstrip() for line in text.split('\n')]
        return '\n'.join(lines).strip()

    def chat_with_context(
        self,
        messages: List[Dict[str, str]],
        tools: Optional[List[Dict]] = None,
    ) -> Union[str, Dict[str, Any]]:
        """Send multi-turn conversation to DeepSeek API."""
        try:
            headers = {
                "Authorization": f"Bearer {self._api_key}",
                "Content-Type": "application/json",
            }

            payload: Dict[str, Any] = {
                "model": DEEPSEEK_CONFIG["default_model"],
                "messages": messages,
                "temperature": DEEPSEEK_CONFIG.get("temperature", 0.3),
                "max_tokens": DEEPSEEK_CONFIG.get("max_tokens", 2000),
            }
            if tools:
                payload["tools"] = tools
                payload["tool_choice"] = "auto"

            response = requests.post(
                f"{DEEPSEEK_CONFIG['base_url']}/chat/completions",
                headers=headers,
                json=payload,
                timeout=DEEPSEEK_CONFIG["timeout"],
            )

            if response.status_code == 200:
                result = response.json()
                choice = result["choices"][0]
                message = choice.get("message", {})
                finish_reason = choice.get("finish_reason", "")
                tool_calls = message.get("tool_calls") or []

                # 1) Canonical path: native tool_calls from API
                if finish_reason == "tool_calls" or tool_calls:
                    if tool_calls:
                        call = tool_calls[0]
                        name = call.get("function", {}).get("name", "")
                        args_raw = call.get("function", {}).get("arguments", "{}")
                        try:
                            args = (
                                json.loads(args_raw)
                                if isinstance(args_raw, str)
                                else (args_raw or {})
                            )
                        except Exception:
                            args = {"command": str(args_raw)}
                        return {
                            "type": "tool_call",
                            "tool_call_id": call.get("id", ""),
                            "name": name,
                            "arguments": args,
                        }
                    # API says tool_calls but field missing: salvage from content
                    content_text = message.get("content", "") or ""
                    parsed = self._tool_parser.parse(content_text)
                    if parsed:
                        return parsed
                    self._log(
                        "[ToolCall Parser] finish_reason=tool_calls but no parseable tool payload found"
                    )
                    return "Agent generated an invalid tool-call payload."

                # 2) Fallback: some models dump tool JSON in content text
                reply = message.get("content", "") or ""
                parsed = self._tool_parser.parse(reply)
                if parsed:
                    return parsed

                return self._clean_markdown(reply)
            else:
                return f"API Error: {response.status_code} - {response.text}"

        except Exception as e:
            return f"Chat request failed: {str(e)}"

    def analyze(
        self,
        verilog_code: str,
        metrics: Dict[str, Any],
        system_prompt: str = "",
    ) -> str:
        """Analyze Verilog code via DeepSeek API."""
        prompt = VerilogMetricsExtractor.build_analysis_prompt(verilog_code, metrics)

        try:
            headers = {
                "Authorization": f"Bearer {self._api_key}",
                "Content-Type": "application/json",
            }

            msg_list: List[Dict[str, str]] = []
            if system_prompt:
                msg_list.append({"role": "system", "content": system_prompt})
            msg_list.append({"role": "user", "content": prompt})

            payload = {
                "model": DEEPSEEK_CONFIG["default_model"],
                "messages": msg_list,
                "temperature": DEEPSEEK_CONFIG.get("temperature", 0.3),
                "max_tokens": DEEPSEEK_CONFIG.get("max_tokens", 2000),
            }

            response = requests.post(
                f"{DEEPSEEK_CONFIG['base_url']}/chat/completions",
                headers=headers,
                json=payload,
                timeout=DEEPSEEK_CONFIG["timeout"],
            )

            if response.status_code == 200:
                result = response.json()
                return result["choices"][0]["message"]["content"]
            else:
                return f"API Error: {response.status_code} - {response.text}"

        except Exception as e:
            fallback = VerilogMetricsExtractor.generate_fallback_analysis(
                verilog_code, metrics
            )
            return (
                f"Analysis failed: {str(e)}\n\n"
                f"(Fallback to basic analysis)\n\n{fallback}"
            )

    def summarize_after_tool(
        self,
        messages: List[Dict[str, str]],
        tool_call_id: str,
        tool_name: str,
        tool_args: Dict[str, Any],
        tool_output: str,
    ) -> Union[str, Dict[str, Any]]:
        """Ask the model to summarize tool execution results."""
        tool_messages = list(messages)
        tool_messages.append({
            "role": "assistant",
            "content": "",
            "tool_calls": [
                {
                    "id": tool_call_id or "call_1",
                    "type": "function",
                    "function": {
                        "name": tool_name,
                        "arguments": json.dumps(tool_args, ensure_ascii=False),
                    },
                }
            ],
        })
        tool_messages.append({
            "role": "tool",
            "tool_call_id": tool_call_id or "call_1",
            "name": tool_name,
            "content": tool_output,
        })
        return self.chat_with_context(tool_messages)
