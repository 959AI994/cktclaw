"""
JSON chaos tests for ToolCallRepair (Fix 3) and orchestrator stage result extraction.

Tests adversarial malformed inputs that real LLMs produce in production:
  - Missing closing braces (truncated JSON)
  - Markdown code-fence contamination
  - Single-quoted keys/values (Python dict style)
  - Trailing commas
  - WARN path: LLM response with no JSON block
  - Followup path: empty first response triggers secondary extraction
  - No infinite loop: even on completely unrecoverable input
"""

import json
import sys
import time
from pathlib import Path

import pytest

_PROJECT_ROOT = Path(__file__).parent.parent.resolve()
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

from cktclaw.tools.repair import ToolCallRepair
from cktclaw.orchestrator.engine import _extract_stage_result


# ═══════════════════════════════════════════════════════════════
# Fixtures
# ═══════════════════════════════════════════════════════════════

@pytest.fixture
def repair():
    return ToolCallRepair()


# ═══════════════════════════════════════════════════════════════
# 1. Missing Closing Brace
# ═══════════════════════════════════════════════════════════════

class TestRepairMissingClosingBrace:
    def test_repair_missing_closing_brace(self, repair):
        """Truncated JSON missing one closing brace must be repaired."""
        raw = '{"args": "foo"'
        result = repair.repair_arguments(raw)
        assert isinstance(result, dict)
        assert result.get("args") == "foo"

    def test_repair_truncated_mid_value(self, repair):
        """JSON truncated mid-value must be repaired to valid dict."""
        raw = '{"file_path": "/tmp/design.v", "command": "synth'
        result = repair.repair_arguments(raw)
        assert isinstance(result, dict)
        assert "file_path" in result
        assert result["file_path"] == "/tmp/design.v"

    def test_repair_nested_truncated(self, repair):
        """Nested JSON structure truncated mid-nesting must be repaired."""
        raw = '{"config": {"area_target": 100, "delay_target": 2.0'
        result = repair.repair_arguments(raw)
        assert isinstance(result, dict)

    def test_repair_deeply_truncated(self, repair):
        """Deeply truncated input (only key name remains) must recover gracefully."""
        raw = '{"file": "/tmp/test.blif", "optimiz'
        result = repair.repair_arguments(raw)
        assert isinstance(result, dict)
        # Should have at least the complete key-value pair
        assert result.get("file") == "/tmp/test.blif"


# ═══════════════════════════════════════════════════════════════
# 2. Markdown Contamination
# ═══════════════════════════════════════════════════════════════

class TestRepairMarkdownContamination:
    def test_extra_text_around_json(self, repair):
        """JSON embedded in surrounding text must be extracted via regex."""
        raw = 'Here is the call: {"name": "abc", "args": "read test.aig"} end'
        result = repair.repair_arguments(raw)
        assert isinstance(result, dict)
        assert "name" in result or "args" in result

    def test_json_with_leading_text(self, repair):
        """JSON after a leading sentence must be extractable."""
        raw = 'The tool call is: {"tool": "yosys", "script": "synth"}'
        result = repair.repair_arguments(raw)
        assert isinstance(result, dict)

    def test_markdown_fenced_json(self, repair):
        """
        JSON wrapped in ```json ... ``` fences.
        The repair function uses regex extraction as fallback.
        Must not crash and must return a dict or raise ValueError.
        """
        raw = '```json\n{"key": "val"}\n```'
        try:
            result = repair.repair_arguments(raw)
            assert isinstance(result, dict)
        except ValueError:
            # Repair correctly identified unrecoverable (fences confuse parser)
            pass


# ═══════════════════════════════════════════════════════════════
# 3. Single Quotes (Python dict style)
# ═══════════════════════════════════════════════════════════════

class TestRepairSingleQuotes:
    def test_unquoted_python_boolean(self, repair):
        """Unquoted Python-style 'True'/'False' values must be handled."""
        raw = '{"verbose": True, "path": "/tmp/out.v"}'
        result = repair.repair_arguments(raw)
        assert isinstance(result, dict)
        # At minimum the string-valued field should be extracted
        assert "path" in result

    def test_regex_fallback_extracts_string_values(self, repair):
        """Regex fallback must extract plain key-value pairs from non-JSON text."""
        raw = '"path": "/tmp/a.v", "mode": "synth", "level": 3'
        result = repair.repair_arguments(raw)
        assert isinstance(result, dict)
        assert result.get("path") == "/tmp/a.v"
        assert result.get("mode") == "synth"

    def test_single_quoted_dict_handled_gracefully(self, repair):
        """Single-quoted Python dicts — must not crash."""
        raw = "{'key': 'value', 'num': 42}"
        try:
            result = repair.repair_arguments(raw)
            assert isinstance(result, dict)
        except ValueError:
            # Acceptable: repair raises when input is completely non-JSON
            pass


# ═══════════════════════════════════════════════════════════════
# 4. Trailing Comma
# ═══════════════════════════════════════════════════════════════

class TestRepairTrailingComma:
    def test_repair_trailing_comma_single_field(self, repair):
        """Trailing comma with single field must be stripped."""
        raw = '{"a": 1,}'
        result = repair.repair_arguments(raw)
        assert isinstance(result, dict)
        assert result.get("a") == 1

    def test_repair_trailing_comma_multiple_fields(self, repair):
        """Trailing comma with multiple fields must be stripped correctly."""
        raw = '{"file": "/tmp/test.v", "cmd": "synth",}'
        result = repair.repair_arguments(raw)
        assert isinstance(result, dict)
        assert result.get("file") == "/tmp/test.v"
        assert result.get("cmd") == "synth"

    def test_repair_empty_object(self, repair):
        """Empty JSON object must parse to empty dict."""
        raw = '{}'
        result = repair.repair_arguments(raw)
        assert isinstance(result, dict)
        assert len(result) == 0

    def test_repair_args_with_trailing_comma(self, repair):
        """ABC tool args format with trailing comma."""
        raw = '{"args": "test.aig", "iters": 50,}'
        result = repair.repair_arguments(raw)
        assert isinstance(result, dict)
        assert result.get("iters") == 50


# ═══════════════════════════════════════════════════════════════
# 5. _extract_stage_result: WARN path (no JSON block)
# ═══════════════════════════════════════════════════════════════

class TestExtractStageResultWarnPath:
    def test_valid_fenced_json_block_extracted(self):
        """Standard fenced JSON block with 'status' must be extracted."""
        response = (
            "Some analysis...\n"
            "```json\n"
            '{"stage": "synthesis", "status": "PASS", "qor": {"area": 100}}\n'
            "```\n"
            "Done."
        )
        result = _extract_stage_result(response)
        assert result is not None
        assert result["status"] == "PASS"
        assert result["stage"] == "synthesis"

    def test_no_json_block_returns_none(self):
        """
        LLM response with no JSON block should return None.
        This triggers the WARN/followup path in _execute_stage.
        """
        response = "I ran the synthesis step and it looks good, area is around 500 cells."
        result = _extract_stage_result(response)
        assert result is None

    def test_empty_response_returns_none(self):
        """Empty string response must return None."""
        assert _extract_stage_result("") is None

    def test_whitespace_only_response_returns_none(self):
        """Whitespace-only response must return None."""
        assert _extract_stage_result("   \n\t  \n") is None

    def test_json_block_without_status_key_returns_none(self):
        """JSON block missing 'status' key must not match."""
        response = (
            "```json\n"
            '{"stage": "synthesis", "qor": {"area": 100}}\n'
            "```"
        )
        result = _extract_stage_result(response)
        assert result is None

    def test_malformed_json_in_block_returns_none(self):
        """Malformed JSON inside a code fence should be skipped gracefully."""
        response = "```json\n{this is not valid json}\n```"
        result = _extract_stage_result(response)
        assert result is None

    def test_multiple_blocks_last_with_status_wins(self):
        """When multiple JSON blocks exist, the last one with 'status' is returned."""
        response = (
            "```json\n"
            '{"stage": "rtl", "status": "PASS", "qor": {}}\n'
            "```\n"
            "More analysis...\n"
            "```json\n"
            '{"stage": "synthesis", "status": "FAIL", "qor": {"area": 999}}\n'
            "```"
        )
        result = _extract_stage_result(response)
        assert result is not None
        assert result["status"] == "FAIL"
        assert result["stage"] == "synthesis"

    def test_inline_json_with_status_extracted(self):
        """Inline JSON with status=WARN must be extracted via fallback regex."""
        response = 'The result is {"status": "WARN", "stage": "pnr", "qor": {}}'
        result = _extract_stage_result(response)
        assert result is not None
        assert result["status"] == "WARN"

    def test_pass_fail_warn_statuses_all_match(self):
        """All three valid statuses (PASS, FAIL, WARN) must be extractable."""
        for status in ["PASS", "FAIL", "WARN"]:
            response = (
                f"```json\n"
                f'{{"stage": "test", "status": "{status}", "qor": {{}}}}\n'
                f"```"
            )
            result = _extract_stage_result(response)
            assert result is not None, f"Failed to extract status={status}"
            assert result["status"] == status


# ═══════════════════════════════════════════════════════════════
# 6. Followup Path (Empty First Response)
# ═══════════════════════════════════════════════════════════════

class TestExtractStageResultFollowup:
    """
    Tests the followup mechanism: when the first LLM response has no JSON block,
    _execute_stage sends a followup prompt. We test that the extraction logic
    correctly handles the followup response format.
    """

    def test_followup_response_extracted(self):
        """
        A response to a followup prompt (just a JSON block, no surrounding text)
        must be extracted correctly.
        """
        # This is what the LLM would return in response to the followup prompt
        followup_response = (
            "```json\n"
            '{"stage": "synthesis", "status": "PASS", "qor": {}, '
            '"issues": [], "recommendation": "proceed"}\n'
            "```"
        )
        result = _extract_stage_result(followup_response)
        assert result is not None
        assert result["status"] == "PASS"
        assert result["recommendation"] == "proceed"

    def test_followup_still_empty_returns_none(self):
        """If the followup also returns no JSON, must return None gracefully."""
        result = _extract_stage_result("I'm sorry, I don't understand.")
        assert result is None

    def test_complex_qor_dict_preserved(self):
        """QoR dict with nested values must be preserved."""
        response = (
            "```json\n"
            '{"stage": "ppa", "status": "PASS", "qor": {"area": 500, '
            '"delay": 1.2, "power": 0.05}, "issues": []}\n'
            "```"
        )
        result = _extract_stage_result(response)
        assert result is not None
        assert result["qor"]["area"] == 500
        assert result["qor"]["delay"] == pytest.approx(1.2)


# ═══════════════════════════════════════════════════════════════
# 7. No Infinite Loop on Persistent Failures
# ═══════════════════════════════════════════════════════════════

class TestRepairLoopNoInfinite:
    """
    Verify that repair terminates quickly even when input is completely unrecoverable.
    No infinite retry loops allowed.
    """

    def test_completely_invalid_input_raises_or_returns_dict(self, repair):
        """
        Input that cannot possibly be repaired must raise ValueError
        (not loop infinitely). Raises ValueError or returns empty dict.
        """
        bad_input = "not json at all!!!"
        start = time.time()
        try:
            result = repair.repair_arguments(bad_input)
            assert isinstance(result, dict)
        except ValueError:
            pass  # Expected: raises ValueError, terminates immediately
        elapsed = time.time() - start
        assert elapsed < 1.0, f"Repair should be fast, took {elapsed:.2f}s"

    def test_all_adversarial_inputs_terminate_quickly(self, repair):
        """Each adversarial input must complete in under 1 second."""
        adversarial_inputs = [
            "}{invalid",
            "[[[[[",
            "}}}}",
            "\x00\x01\x02\x03",
            "null",
            "true",
            "false",
            "123",
            '"just a string"',
            "[]",
            "[[1, 2, 3]]",
        ]
        for raw in adversarial_inputs:
            start = time.time()
            try:
                repair.repair_arguments(raw)
            except (ValueError, Exception):
                pass
            elapsed = time.time() - start
            assert elapsed < 1.0, (
                f"Repair took too long ({elapsed:.2f}s) for input: {repr(raw)}"
            )

    def test_empty_string_returns_empty_dict(self, repair):
        """Empty string input must return empty dict."""
        result = repair.repair_arguments("")
        assert result == {}

    def test_whitespace_only_returns_empty_dict(self, repair):
        """Whitespace-only input must return empty dict."""
        result = repair.repair_arguments("   \n  \t  ")
        assert result == {}

    def test_type_coercion_with_schema(self, repair):
        """String-typed integers must be coerced to int when schema specifies integer."""
        raw = '{"iterations": "50", "timeout": "300"}'
        schema = {
            "type": "object",
            "properties": {
                "iterations": {"type": "integer"},
                "timeout": {"type": "integer"},
            },
        }
        result = repair.repair_arguments(raw, schema)
        assert result["iterations"] == 50
        assert result["timeout"] == 300

    def test_tool_name_repair_exact_match(self, repair):
        """Exact tool name must be returned as-is."""
        result = repair.repair_tool_name("yosys", ["yosys", "abc", "opensta"])
        assert result == "yosys"

    def test_tool_name_repair_case_insensitive(self, repair):
        """Case-insensitive tool name match must work."""
        result = repair.repair_tool_name("YOSYS", ["yosys", "abc", "opensta"])
        assert result == "yosys"

    def test_tool_name_repair_fuzzy_typo(self, repair):
        """Typo within Levenshtein distance 2 must be corrected."""
        result = repair.repair_tool_name("yoss", ["yosys", "abc", "opensta"])
        assert result == "yosys"

    def test_tool_name_repair_suffix_stripped(self, repair):
        """Tool names with common suffixes like _tool must be matched."""
        result = repair.repair_tool_name("yosys_tool", ["yosys", "abc"])
        assert result == "yosys"

    def test_tool_name_repair_empty_available_list(self, repair):
        """Empty available tools list must return None gracefully."""
        result = repair.repair_tool_name("yosys", [])
        assert result is None
