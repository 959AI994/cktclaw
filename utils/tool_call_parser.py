"""
ToolCallParser - Multi-strategy tool call extraction from LLM text output.

Handles malformed JSON from weak local models with multiple fallback strategies:
1. Markdown code block extraction
2. Balanced brace scanning
3. Pure JSON parsing
4. TOOL_CALL: prefix extraction
5. Known tool name scanning
6. ast.literal_eval fallback
7. Regex salvage for broken quotes
"""

import ast
import json
import re
from typing import Any, Dict, List, Optional


# Default allowed tool names
DEFAULT_ALLOWED_TOOLS = [
    "execute_cktclaw_command",
    "ai4eda",
    "abc",
    "yosys",
    "reverse",
    "opensta",
    "save_session_memory",
]


class ToolCallParser:
    """Parse tool calls from LLM text output with multi-level fallback."""

    def __init__(
        self,
        allowed_tools: Optional[List[str]] = None,
        verbose: bool = False,
    ):
        self.allowed_tools = allowed_tools or DEFAULT_ALLOWED_TOOLS
        self.verbose = verbose

    def _log(self, msg: str) -> None:
        if self.verbose:
            print(msg)

    def parse(self, text: str) -> Optional[Dict[str, Any]]:
        """
        Extract a tool call from LLM text output.

        Returns a normalized dict or None:
        {"type": "tool_call", "tool_call_id": str, "name": str, "arguments": dict}
        """
        if not text:
            return None

        raw = text.strip()

        # Strip wrapping markdown code fence if present
        if raw.startswith("```"):
            lines = raw.split('\n')
            if lines[0].startswith("```"):
                lines = lines[1:]
            if lines and lines[-1].strip() == "```":
                lines = lines[:-1]
            raw = '\n'.join(lines).strip()

        # Path 0.5: ```json ... ``` blocks anywhere in text
        for m in re.finditer(r"```(?:json)?\s*\n?([\s\S]*?)```", text, flags=re.IGNORECASE):
            inner = (m.group(1) or "").strip()
            if not inner.startswith("{"):
                continue
            try:
                maybe = json.loads(inner)
            except Exception:
                continue
            normalized = self._normalize(maybe)
            if normalized:
                return normalized

        # Path 0.6: scan all balanced-brace JSON objects
        for i, ch in enumerate(text):
            if ch != "{":
                continue
            cand = self._extract_balanced_object(text, i)
            if not cand or not cand.endswith("}"):
                continue
            try:
                maybe = json.loads(cand)
            except Exception:
                continue
            normalized = self._normalize(maybe)
            if normalized:
                return normalized

        payload_obj = None

        # Path 0: pure JSON object response
        if raw.startswith("{") and raw.endswith("}"):
            payload_obj = raw

        # Path A: explicit TOOL_CALL prefix
        if payload_obj is None:
            marker = "TOOL_CALL:"
            idx = text.find(marker)
            if idx >= 0:
                seg = text[idx + len(marker):]
                bidx = seg.find("{")
                if bidx >= 0:
                    payload_obj = self._extract_balanced_object(seg, bidx)

        # Path B: contains known tool names
        if payload_obj is None:
            for tool_name in self.allowed_tools:
                if tool_name in text:
                    tool_idx = text.find(tool_name)
                    left = text.rfind("{", 0, tool_idx)
                    if left >= 0:
                        payload_obj = self._extract_balanced_object(text, left)
                        if payload_obj:
                            break

        # Path C: contains type=tool_call signature
        if payload_obj is None and '"type"' in text and "tool_call" in text:
            type_idx = text.find("tool_call")
            left = text.rfind("{", 0, type_idx)
            if left >= 0:
                payload_obj = self._extract_balanced_object(text, left)

        if payload_obj is None:
            return None

        obj = None
        # Attempt 1: strict JSON
        try:
            obj = json.loads(payload_obj)
        except Exception as e1:
            self._log(f"[ToolCall Parser] strict json.loads failed: {e1}")
            # Attempt 2: python literal tolerant parser
            try:
                obj = ast.literal_eval(payload_obj)
            except Exception as e2:
                self._log(f"[ToolCall Parser] ast.literal_eval failed: {e2}")

        # Attempt 3: regex salvage for broken command quotes
        if obj is None:
            try:
                if "execute_cktclaw_command" in payload_obj:
                    cmd_match = re.search(
                        r'"command"\s*:\s*"(.+)"', payload_obj, flags=re.DOTALL
                    )
                    cmd = ""
                    if cmd_match:
                        cmd = cmd_match.group(1)
                        cmd = re.sub(
                            r'"([^"]*?)"',
                            lambda m: f"'{m.group(1)}'",
                            cmd,
                        )
                        cmd = cmd.replace('\\"', '"').strip()
                    if cmd:
                        obj = {
                            "tool_name": "execute_cktclaw_command",
                            "arguments": {"command": cmd},
                        }
            except Exception as e3:
                self._log(f"[ToolCall Parser] regex salvage failed: {e3}")

        if obj is None:
            self._log(
                f"[ToolCall Parser] Could not parse tool call payload: {payload_obj[:300]}"
            )
            return None

        normalized = self._normalize(obj)
        if normalized:
            return normalized
        tool_name = obj.get("tool_name") or obj.get("name") or obj.get("tool")
        if tool_name:
            self._log(f"[ToolCall Parser] Unknown tool name: {tool_name}")
        return None

    # ── Helper methods ──

    @staticmethod
    def _extract_balanced_object(s: str, start_idx: int) -> Optional[str]:
        """Extract a balanced JSON object starting at start_idx."""
        if start_idx < 0 or start_idx >= len(s) or s[start_idx] != "{":
            return None
        depth = 0
        for i in range(start_idx, len(s)):
            ch = s[i]
            if ch == "{":
                depth += 1
            elif ch == "}":
                depth -= 1
                if depth == 0:
                    return s[start_idx:i + 1]
        return None

    def _normalize(self, obj: Any) -> Optional[Dict[str, Any]]:
        """Normalize a parsed dict into a standard tool_call structure."""
        if not isinstance(obj, dict):
            return None
        tool_name = obj.get("tool_name") or obj.get("name") or obj.get("tool")
        args = obj.get("arguments") or obj.get("args") or {}
        if isinstance(args, str):
            args_s = args.strip()
            if args_s.startswith("{") and args_s.endswith("}"):
                try:
                    args = json.loads(args_s)
                except Exception:
                    try:
                        args = ast.literal_eval(args_s)
                    except Exception:
                        args = {"args": args_s}
            else:
                args = {"args": args_s}
        if not tool_name or str(tool_name) not in self.allowed_tools:
            return None
        if not isinstance(args, dict):
            args = {"command": str(args)}
        return {
            "type": "tool_call",
            "tool_call_id": "local_call_1",
            "name": str(tool_name),
            "arguments": args,
        }
