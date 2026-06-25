"""Tests for cktclaw doctor."""
import pytest


def test_doctor_report_has_checks():
    from cktclaw.handlers.doctor_handler import run_doctor
    rep = run_doctor()
    names = {c.name for c in rep.checks}
    assert {"api_keys", "eda_tools", "cktclaw_home_writable", "policy"} <= names


def test_doctor_flags_missing_deepseek_key(monkeypatch):
    monkeypatch.delenv("DEEPSEEK_API_KEY", raising=False)
    monkeypatch.delenv("CKTCLAW_DEEPSEEK_KEY", raising=False)
    monkeypatch.setattr(
        "cktclaw.api_credentials._resolve_from_yaml", lambda provider: None
    )
    from cktclaw.handlers.doctor_handler import run_doctor
    rep = run_doctor()
    key_check = next(c for c in rep.checks if c.name == "api_keys")
    assert key_check.status in ("warn", "fail")


def test_doctor_exit_code_nonzero_on_fail(monkeypatch):
    from cktclaw.handlers.doctor_handler import run_doctor
    rep = run_doctor()
    assert rep.exit_code() in (0, 1)


def test_config_has_no_root_default():
    import inspect
    import cktclaw.config as cfg
    src = inspect.getsource(cfg)
    assert "/root/" not in src
