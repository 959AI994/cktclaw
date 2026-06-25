"""
Tool Call Repair -- fixes malformed tool call arguments from LLMs.

Handles common issues:
1. Truncated JSON (missing closing braces/brackets)
2. Trailing commas
3. Wrong types (str->int, str->bool coercion)
4. Missing required fields (fills with defaults)
5. Misspelled tool names (fuzzy matching)
"""

import json
import logging
import re
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


class ToolCallRepair:
    """
    Repairs malformed tool call arguments and names.

    Usage:
        repair = ToolCallRepair()
        fixed_args = repair.repair_arguments(raw_json, tool_schema)
        fixed_name = repair.repair_tool_name(name, available_tools)
    """

    def repair_arguments(
        self,
        raw_json: str,
        tool_schema: Optional[Dict] = None,
    ) -> Dict[str, Any]:
        """
        Attempt to parse and repair malformed JSON arguments.

        Strategy:
        1. Try json.loads directly
        2. If fails: attempt trailing-brace fix
        3. If still fails: strip trailing comma
        4. If still fails: regex key-value extraction
        5. Validate and coerce types against schema

        Args:
            raw_json: Raw JSON string from LLM (may be malformed).
            tool_schema: Optional JSON Schema for the tool parameters.

        Returns:
            Parsed arguments dict (best-effort).

        Raises:
            ValueError: If JSON is completely unrecoverable.
        """
        if not raw_json or not raw_json.strip():
            return {}

        raw_json = raw_json.strip()

        # Strategy 1: direct parse
        try:
            result = json.loads(raw_json)
            if isinstance(result, dict):
                return self._coerce_types(result, tool_schema)
            return {}
        except json.JSONDecodeError:
            pass

        # Strategy 2: fix trailing braces/brackets
        fixed = self._fix_truncated_json(raw_json)
        if fixed:
            try:
                result = json.loads(fixed)
                if isinstance(result, dict):
                    logger.info("Tool call repaired via brace-fixing")
                    return self._coerce_types(result, tool_schema)
            except json.JSONDecodeError:
                pass

        # Strategy 3: strip trailing comma and fix
        stripped = self._strip_trailing_comma(raw_json)
        fixed = self._fix_truncated_json(stripped)
        if fixed:
            try:
                result = json.loads(fixed)
                if isinstance(result, dict):
                    logger.info("Tool call repaired via comma-strip + brace-fix")
                    return self._coerce_types(result, tool_schema)
            except json.JSONDecodeError:
                pass

        # Strategy 4: regex extraction
        extracted = self._regex_extract(raw_json)
        if extracted:
            logger.info("Tool call repaired via regex extraction")
            return self._coerce_types(extracted, tool_schema)

        raise ValueError(
            "Could not repair tool call arguments: " + raw_json[:100]
        )

    def repair_tool_name(
        self,
        name: str,
        available_tools: List[str],
    ) -> Optional[str]:
        """
        Fuzzy-match a tool name against registered tools.

        Uses Levenshtein distance <= 2 to find the closest match.
        Handles common LLM typos.

        Args:
            name: The (possibly misspelled) tool name.
            available_tools: List of valid tool names.

        Returns:
            Corrected tool name, or None if no close match found.
        """
        if not name or not available_tools:
            return None

        # Exact match
        if name in available_tools:
            return name

        # Lowercase exact match
        name_lower = name.lower()
        for tool in available_tools:
            if tool.lower() == name_lower:
                return tool

        # Common prefix/suffix variations
        for tool in available_tools:
            # Handle "abc_tool" -> "abc" or "yosys_run" -> "yosys"
            # Strip common suffixes like _tool, _run
            name_base = re.sub(r'[_-](tool|run|exec|cmd)$', '', name_lower)
            tool_base = re.sub(r'[_-](tool|run|exec|cmd)$', '', tool.lower())
            if name_base == tool_base:
                return tool
            if name_lower.startswith(tool.lower()) or tool.lower().startswith(name_lower):
                if abs(len(name) - len(tool)) <= 5:
                    return tool

        # Levenshtein distance <= 2
        best_match = None
        best_distance = 3  # Max acceptable distance

        for tool in available_tools:
            dist = self._levenshtein(name_lower, tool.lower())
            if dist < best_distance:
                best_distance = dist
                best_match = tool

        return best_match

    @staticmethod
    def _fix_truncated_json(s: str) -> Optional[str]:
        """Add missing closing braces/brackets to truncated JSON."""
        # Count open vs close braces/brackets
        open_braces = s.count('{') - s.count('}')
        open_brackets = s.count('[') - s.count(']')

        if open_braces < 0 or open_brackets < 0:
            return None  # More closes than opens -- not truncated

        if open_braces == 0 and open_brackets == 0:
            return s  # Already balanced

        # If we're inside an unterminated string, close it
        # Count unescaped quotes
        in_string = False
        last_char = ''
        for ch in s:
            if ch == '"' and last_char != '\\':
                in_string = not in_string
            last_char = ch

        if in_string:
            s = s + '"'

        # Strip any incomplete value at the end (e.g., trailing key without value)
        s = re.sub(r',\s*"[^"]*$', '', s)  # Remove partial key at end
        s = re.sub(r',\s*$', '', s)  # Remove trailing comma

        # Recount after modifications
        open_braces = s.count('{') - s.count('}')
        open_brackets = s.count('[') - s.count(']')

        # Add closing brackets/braces
        result = s + (']' * max(0, open_brackets)) + ('}' * max(0, open_braces))
        return result

    @staticmethod
    def _strip_trailing_comma(s: str) -> str:
        """Remove trailing commas before closing braces/brackets."""
        return re.sub(r',\s*([}\]])', r'\1', s)

    @staticmethod
    def _regex_extract(s: str) -> Optional[Dict[str, Any]]:
        """
        Last-resort: extract key-value pairs using regex.

        Handles patterns like: "key": "value" or "key": 123
        """
        result = {}

        # Match "key": "value"
        string_pairs = re.findall(r'"(\w+)"\s*:\s*"([^"]*)"', s)
        for key, value in string_pairs:
            result[key] = value

        # Match "key": number
        num_pairs = re.findall(r'"(\w+)"\s*:\s*(\d+(?:\.\d+)?)', s)
        for key, value in num_pairs:
            if key not in result:
                if '.' in value:
                    result[key] = float(value)
                else:
                    result[key] = int(value)

        # Match "key": true/false
        bool_pairs = re.findall(r'"(\w+)"\s*:\s*(true|false)', s, re.IGNORECASE)
        for key, value in bool_pairs:
            if key not in result:
                result[key] = value.lower() == 'true'

        return result if result else None

    @staticmethod
    def _coerce_types(
        args: Dict[str, Any],
        schema: Optional[Dict] = None,
    ) -> Dict[str, Any]:
        """Coerce argument types to match schema expectations."""
        if not schema:
            return args

        properties = schema.get("properties", {})
        result = dict(args)

        for key, value in result.items():
            if key not in properties:
                continue

            expected_type = properties[key].get("type")
            if expected_type is None:
                continue

            try:
                if expected_type == "integer" and isinstance(value, str):
                    result[key] = int(value)
                elif expected_type == "number" and isinstance(value, str):
                    result[key] = float(value)
                elif expected_type == "boolean" and isinstance(value, str):
                    result[key] = value.lower() in ("true", "1", "yes")
                elif expected_type == "string" and not isinstance(value, str):
                    result[key] = str(value)
            except (ValueError, TypeError):
                pass  # Keep original value if coercion fails

        # Fill missing required fields with defaults
        required = schema.get("required", [])
        for field in required:
            if field not in result and field in properties:
                default = properties[field].get("default")
                if default is not None:
                    result[field] = default

        return result

    @staticmethod
    def _levenshtein(s1: str, s2: str) -> int:
        """Compute Levenshtein edit distance between two strings."""
        if len(s1) < len(s2):
            return ToolCallRepair._levenshtein(s2, s1)

        if len(s2) == 0:
            return len(s1)

        prev_row = list(range(len(s2) + 1))

        for i, c1 in enumerate(s1):
            curr_row = [i + 1]
            for j, c2 in enumerate(s2):
                # Cost of insertion, deletion, substitution
                insertions = prev_row[j + 1] + 1
                deletions = curr_row[j] + 1
                substitutions = prev_row[j] + (c1 != c2)
                curr_row.append(min(insertions, deletions, substitutions))
            prev_row = curr_row

        return prev_row[-1]
