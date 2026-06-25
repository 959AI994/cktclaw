"""Tests for audit trail."""
import json
import pytest
from pathlib import Path


def test_audit_event_appended_as_jsonl(tmp_path, monkeypatch):
    monkeypatch.setenv("CKTCLAW_HOME", str(tmp_path))
    from cktclaw.runtime.run_context import new_run
    from cktclaw.runtime.audit import audit_event
    r = new_run(kind="chat")
    with r.activate():
        audit_event(kind="tool_call", capability="yosys", status="ok")
        audit_event(kind="tool_call", capability="abc", status="error")
    lines = (r.dir / "events.jsonl").read_text().strip().splitlines()
    assert len(lines) == 2
    assert json.loads(lines[0])["capability"] == "yosys"


def test_audit_redacts_api_key(tmp_path, monkeypatch):
    monkeypatch.setenv("CKTCLAW_HOME", str(tmp_path))
    from cktclaw.runtime.run_context import new_run
    from cktclaw.runtime.audit import audit_event
    r = new_run(kind="chat")
    with r.activate():
        audit_event(kind="llm_call", capability="deepseek",
                    extra={"authorization": "Bearer sk-secret123"}, status="ok")
    text = (r.dir / "events.jsonl").read_text()
    assert "sk-secret123" not in text
    assert "REDACTED" in text


def test_audit_args_are_digested_not_raw(tmp_path, monkeypatch):
    monkeypatch.setenv("CKTCLAW_HOME", str(tmp_path))
    from cktclaw.runtime.run_context import new_run
    from cktclaw.runtime.audit import audit_event
    r = new_run(kind="chat")
    with r.activate():
        audit_event(kind="tool_call", capability="yosys",
                    args={"args": "read_verilog secret_design.v"}, status="ok")
    ev = json.loads((r.dir / "events.jsonl").read_text().strip())
    assert "args_digest" in ev
    assert "secret_design" not in json.dumps(ev)


def test_audit_noop_without_active_run(tmp_path, monkeypatch):
    monkeypatch.setenv("CKTCLAW_HOME", str(tmp_path))
    from cktclaw.runtime.audit import audit_event
    audit_event(kind="tool_call", capability="x", status="ok")  # must not raise
