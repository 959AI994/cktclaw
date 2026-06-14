"""
Tests for v2.1 architecture components:
- Tool Guardrails
- Trajectory Logging
- YAML Config Loader
- Delegation Tool
- Error Classification
"""

import asyncio
import json
import tempfile
from pathlib import Path
from typing import Any, Dict

import pytest

from cktclaw.tools.guardrails import ToolGuardrails, GuardrailViolation
from cktclaw.trajectory import TrajectoryLogger
from cktclaw.config_loader import CktClawConfig, ensure_config_file


# ━━━━━━━━━━ Tool Guardrails Tests ━━━━━━━━━━


class TestToolGuardrails:
    def test_allows_first_call(self):
        g = ToolGuardrails()
        result = g.check("yosys", {"script": "read_verilog f.v"})
        assert result is None

    def test_allows_different_args(self):
        g = ToolGuardrails()
        g.check("yosys", {"script": "read_verilog a.v"})
        g.check("yosys", {"script": "read_verilog b.v"})
        result = g.check("yosys", {"script": "read_verilog c.v"})
        assert result is None

    def test_blocks_after_max_duplicates(self):
        g = ToolGuardrails(max_duplicates=3)
        args = {"script": "same_command"}

        # First 3 should pass
        assert g.check("yosys", args) is None
        assert g.check("yosys", args) is None
        assert g.check("yosys", args) is None

        # 4th identical call should be blocked
        violation = g.check("yosys", args)
        assert violation is not None
        assert violation.reason == "repeated_identical_call"
        assert "yosys" in violation.tool_name

    def test_per_turn_limit(self):
        g = ToolGuardrails(per_turn_limit=5)
        for i in range(5):
            assert g.check("tool", {"i": i}) is None

        # 6th call should be blocked
        violation = g.check("tool", {"i": 99})
        assert violation is not None
        assert violation.reason == "per_turn_limit_exceeded"

    def test_reset_clears_state(self):
        g = ToolGuardrails(max_duplicates=2)
        args = {"x": 1}
        g.check("t", args)
        g.check("t", args)

        # Would be blocked
        assert g.check("t", args) is not None

        # After reset, should pass again
        g.reset()
        assert g.check("t", args) is None

    def test_truncate_output_short(self):
        g = ToolGuardrails(max_output_chars=100)
        output = "short output"
        assert g.truncate_output(output) == output

    def test_truncate_output_long(self):
        g = ToolGuardrails(max_output_chars=50)
        output = "x" * 200
        result = g.truncate_output(output, "test_tool")
        assert len(result) < 200
        assert "[OUTPUT TRUNCATED" in result
        assert result.startswith("x" * 50)

    def test_total_calls_tracking(self):
        g = ToolGuardrails()
        assert g.total_calls == 0
        g.check("a", {"x": 1})
        g.check("b", {"x": 2})
        assert g.total_calls == 2

    def test_call_summary(self):
        g = ToolGuardrails()
        g.check("abc", {"cmd": "balance"})
        g.check("abc", {"cmd": "balance"})
        g.check("yosys", {"script": "synth"})

        summary = g.call_summary
        assert len(summary) == 2
        names = [s["name"] for s in summary]
        assert "abc" in names
        assert "yosys" in names


# ━━━━━━━━━━ Trajectory Logger Tests ━━━━━━━━━━


class TestTrajectoryLogger:
    def test_log_user_message(self, tmp_path):
        tl = TrajectoryLogger(base_dir=tmp_path)
        tl.log_user_message("session-1", "hello world")

        events = tl.get_session_events("session-1")
        assert len(events) == 1
        assert events[0]["event_type"] == "user_message"
        assert events[0]["data"]["content"] == "hello world"

    def test_log_tool_call_and_result(self, tmp_path):
        tl = TrajectoryLogger(base_dir=tmp_path)
        tl.log_tool_call("s1", "yosys", {"script": "stat"})
        tl.log_tool_result("s1", "yosys", "Area: 100", success=True)

        events = tl.get_session_events("s1")
        assert len(events) == 2
        assert events[0]["event_type"] == "tool_call"
        assert events[0]["data"]["tool_name"] == "yosys"
        assert events[1]["event_type"] == "tool_result"
        assert events[1]["data"]["success"] is True

    def test_log_error(self, tmp_path):
        tl = TrajectoryLogger(base_dir=tmp_path)
        tl.log_error("s1", "timeout", category="transient")

        events = tl.get_session_events("s1")
        assert len(events) == 1
        assert events[0]["data"]["category"] == "transient"

    def test_log_assistant_message(self, tmp_path):
        tl = TrajectoryLogger(base_dir=tmp_path)
        tl.log_assistant_message("s1", "Here is the result", provider="deepseek", elapsed=1.5)

        events = tl.get_session_events("s1")
        assert len(events) == 1
        assert events[0]["data"]["provider"] == "deepseek"
        assert events[0]["data"]["elapsed_seconds"] == 1.5

    def test_multiple_sessions_isolated(self, tmp_path):
        tl = TrajectoryLogger(base_dir=tmp_path)
        tl.log_user_message("a", "msg-a")
        tl.log_user_message("b", "msg-b")

        assert len(tl.get_session_events("a")) == 1
        assert len(tl.get_session_events("b")) == 1

    def test_jsonl_format(self, tmp_path):
        tl = TrajectoryLogger(base_dir=tmp_path)
        tl.log_user_message("s1", "line1")
        tl.log_user_message("s1", "line2")

        filepath = tmp_path / "s1.jsonl"
        assert filepath.exists()
        lines = filepath.read_text().strip().split("\n")
        assert len(lines) == 2
        # Each line must be valid JSON
        for line in lines:
            json.loads(line)

    def test_empty_session(self, tmp_path):
        tl = TrajectoryLogger(base_dir=tmp_path)
        assert tl.get_session_events("nonexistent") == []


# ━━━━━━━━━━ Config Loader Tests ━━━━━━━━━━


class TestCktClawConfig:
    def _write_config(self, tmp_path, content: str) -> Path:
        config_file = tmp_path / "config.yaml"
        config_file.write_text(content, encoding="utf-8")
        return config_file

    def test_load_basic(self, tmp_path):
        path = self._write_config(tmp_path, """
guardrails:
  max_duplicate_calls: 5
  max_output_chars: 10000
""")
        cfg = CktClawConfig(config_path=path)
        assert cfg.guardrails_max_duplicates == 5
        assert cfg.guardrails_max_output == 10000

    def test_dotted_key_access(self, tmp_path):
        path = self._write_config(tmp_path, """
llm:
  default_provider: claude
  failover_chain:
    - claude
    - openai
""")
        cfg = CktClawConfig(config_path=path)
        assert cfg.get("llm.default_provider") == "claude"
        assert cfg.get_list("llm.failover_chain") == ["claude", "openai"]

    def test_defaults_on_missing_file(self, tmp_path):
        cfg = CktClawConfig(config_path=tmp_path / "nonexistent.yaml")
        assert cfg.guardrails_max_duplicates == 3
        assert cfg.agent_max_turns == 12
        assert cfg.trajectory_enabled is True

    def test_defaults_on_missing_key(self, tmp_path):
        path = self._write_config(tmp_path, "llm:\n  default_provider: openai\n")
        cfg = CktClawConfig(config_path=path)
        # Key exists
        assert cfg.default_provider == "openai"
        # Key doesn't exist — should return default
        assert cfg.guardrails_max_duplicates == 3

    def test_get_bool(self, tmp_path):
        path = self._write_config(tmp_path, """
trajectory:
  enabled: false
""")
        cfg = CktClawConfig(config_path=path)
        assert cfg.trajectory_enabled is False

    def test_security_config(self, tmp_path):
        path = self._write_config(tmp_path, """
security:
  allowed_paths:
    - /home/user/project
  blocked_patterns:
    - /etc/shadow
""")
        cfg = CktClawConfig(config_path=path)
        assert "/home/user/project" in cfg.security_allowed_paths
        assert "/etc/shadow" in cfg.security_blocked_patterns


# ━━━━━━━━━━ Delegate Tool Tests ━━━━━━━━━━


class TestDelegateToolSchema:
    def test_tool_schema(self):
        from cktclaw.tools.agent.delegate_tool import DelegateTaskTool

        tool = DelegateTaskTool()
        assert tool.name == "delegate_task"
        assert tool.category == "agent"

        schema = tool.to_openai_schema()
        assert schema["type"] == "function"
        assert "task" in schema["function"]["parameters"]["properties"]
        assert "task" in schema["function"]["parameters"]["required"]

    def test_validate_empty_task(self):
        from cktclaw.tools.agent.delegate_tool import DelegateTaskTool
        from cktclaw.tools.base import ToolContext

        tool = DelegateTaskTool()
        result = asyncio.run(tool.execute({"task": ""}, ToolContext(session_id="test")))
        assert not result.success
        assert "required" in result.error.lower()


# ━━━━━━━━━━ Error Classification Tests ━━━━━━━━━━


class TestErrorClassification:
    def test_context_overflow(self):
        from cktclaw.handlers.chat_handler_v3 import classify_error, ErrorCategory

        err = Exception("This model's maximum context length is 128000 tokens")
        assert classify_error(err) == ErrorCategory.CONTEXT_OVERFLOW

    def test_rate_limit(self):
        from cktclaw.handlers.chat_handler_v3 import classify_error, ErrorCategory

        err = Exception("429 Too Many Requests: rate limit exceeded")
        assert classify_error(err) == ErrorCategory.TRANSIENT

    def test_timeout(self):
        from cktclaw.handlers.chat_handler_v3 import classify_error, ErrorCategory

        err = Exception("Connection timeout after 30s")
        assert classify_error(err) == ErrorCategory.TRANSIENT

    def test_unauthorized(self):
        from cktclaw.handlers.chat_handler_v3 import classify_error, ErrorCategory

        err = Exception("401 Unauthorized: invalid api key")
        assert classify_error(err) == ErrorCategory.PERMANENT

    def test_service_unavailable(self):
        from cktclaw.handlers.chat_handler_v3 import classify_error, ErrorCategory

        err = Exception("503 Service Unavailable")
        assert classify_error(err) == ErrorCategory.TRANSIENT


# ━━━━━━━━━━ RetryState Tests ━━━━━━━━━━


class TestRetryState:
    def test_initial_state(self):
        from cktclaw.handlers.chat_handler_v3 import RetryState

        rs = RetryState(max_retries=3)
        assert rs.can_retry
        assert rs.attempts == 0

    def test_exhausted_retries(self):
        from cktclaw.handlers.chat_handler_v3 import RetryState

        rs = RetryState(max_retries=2)
        rs.record_attempt("err1")
        assert rs.can_retry
        rs.record_attempt("err2")
        assert not rs.can_retry

    def test_backoff_increases(self):
        from cktclaw.handlers.chat_handler_v3 import RetryState

        rs = RetryState(base_delay=1.0)
        rs.record_attempt("e1")
        d1 = rs.get_backoff_delay()
        rs.record_attempt("e2")
        d2 = rs.get_backoff_delay()
        # Second delay should be roughly 2x the first (with jitter)
        assert d2 > d1

    def test_reset(self):
        from cktclaw.handlers.chat_handler_v3 import RetryState

        rs = RetryState(max_retries=2)
        rs.record_attempt("err")
        rs.record_attempt("err")
        assert not rs.can_retry
        rs.reset()
        assert rs.can_retry
        assert rs.attempts == 0
