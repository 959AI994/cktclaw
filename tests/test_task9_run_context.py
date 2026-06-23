"""Tests for RunContext + run directory."""
import json
import pytest
from pathlib import Path


def test_new_run_creates_unique_id(tmp_path, monkeypatch):
    monkeypatch.setenv("CKTCLAW_HOME", str(tmp_path))
    from cktclaw.runtime.run_context import new_run
    r1 = new_run(kind="chat")
    r2 = new_run(kind="chat")
    assert r1.run_id != r2.run_id


def test_new_run_creates_directory(tmp_path, monkeypatch):
    monkeypatch.setenv("CKTCLAW_HOME", str(tmp_path))
    from cktclaw.runtime.run_context import new_run
    r = new_run(kind="loop")
    assert r.dir.is_dir()
    assert (r.dir / "logs").is_dir()
    assert (r.dir / "meta.json").is_file()


def test_get_current_run_returns_active(tmp_path, monkeypatch):
    monkeypatch.setenv("CKTCLAW_HOME", str(tmp_path))
    from cktclaw.runtime.run_context import new_run, get_current_run
    r = new_run(kind="orchestrator")
    with r.activate():
        assert get_current_run() is r


def test_get_current_run_none_when_inactive(tmp_path, monkeypatch):
    monkeypatch.setenv("CKTCLAW_HOME", str(tmp_path))
    from cktclaw.runtime.run_context import get_current_run
    assert get_current_run() is None


def test_meta_records_kind_user_timestamp(tmp_path, monkeypatch):
    monkeypatch.setenv("CKTCLAW_HOME", str(tmp_path))
    from cktclaw.runtime.run_context import new_run
    r = new_run(kind="chat")
    meta = json.loads((r.dir / "meta.json").read_text())
    assert meta["kind"] == "chat"
    assert "user" in meta and "started_at" in meta and "run_id" in meta
