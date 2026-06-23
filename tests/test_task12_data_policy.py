"""Tests for IP/data egress control."""
import json
import pytest


def test_offline_mode_blocks_cloud_provider(monkeypatch):
    monkeypatch.setenv("CKTCLAW_OFFLINE", "1")
    from cktclaw.runtime.data_policy import EgressGuard
    g = EgressGuard()
    d = g.check_provider("deepseek")
    assert not d.allowed and "offline" in d.reason.lower()


def test_offline_mode_allows_local(monkeypatch):
    monkeypatch.setenv("CKTCLAW_OFFLINE", "1")
    from cktclaw.runtime.data_policy import EgressGuard
    assert EgressGuard().check_provider("local").allowed


def test_classify_detects_rtl():
    from cktclaw.runtime.data_policy import classify
    rtl = "module adder(input a, b, output sum); assign sum = a + b; endmodule"
    assert classify(rtl) == "design"


def test_redact_design_strips_module_bodies_when_enabled():
    from cktclaw.runtime.data_policy import redact_design
    rtl = "module top(); secret_logic xyz(); endmodule"
    out = redact_design(rtl)
    assert "secret_logic" not in out
    assert "[REDACTED" in out


def test_egress_to_cloud_is_audited(tmp_path, monkeypatch):
    monkeypatch.setenv("CKTCLAW_HOME", str(tmp_path))
    from cktclaw.runtime.run_context import new_run
    from cktclaw.runtime.data_policy import EgressGuard
    r = new_run(kind="chat")
    with r.activate():
        EgressGuard().guard_outbound(provider="deepseek",
                                     content="module x(); endmodule")
    events = (r.dir / "events.jsonl").read_text()
    assert "egress" in events and "design" in events
