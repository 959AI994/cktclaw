"""
RunContext — per-invocation run identity and run directory.

Every top-level invocation (chat turn, /loop, orchestrator run, RTL-CLAW skill)
opens a run with a unique ``run_id`` and a directory::

    <root>/runs/<run_id>/
        meta.json      run metadata (kind, user, timestamps)
        events.jsonl   append-only audit trail (Task 10)
        logs/          run-scoped log files

Root resolution order:
  1. ``$CKTCLAW_HOME``  → ``<CKTCLAW_HOME>/runs/``
  2. project ``./.cktclaw/runs/``

The active run is tracked in a ``ContextVar`` so nested code (audit, budget,
checkpoint) can locate it via :func:`get_current_run` without threading it
through every call.
"""
from __future__ import annotations

import getpass
import json
import os
import uuid
from contextlib import contextmanager
from contextvars import ContextVar
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

_run_var: ContextVar[Optional["RunContext"]] = ContextVar("cktclaw_run", default=None)


def _home_root() -> Path:
    home = os.environ.get("CKTCLAW_HOME")
    if home:
        return Path(home)
    return Path.cwd() / ".cktclaw"


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


class RunContext:
    """Identity + on-disk artifacts for a single top-level invocation."""

    def __init__(self, kind: str, run_id: str, directory: Path, user: str):
        self.kind = kind
        self.run_id = run_id
        self.dir = directory
        self.user = user
        self.started_at = _utc_now_iso()
        self._token = None

    @property
    def events_path(self) -> Path:
        return self.dir / "events.jsonl"

    def log_path(self, name: str) -> Path:
        return self.dir / "logs" / name

    def write_meta(self, **extra) -> None:
        meta = {
            "run_id": self.run_id,
            "kind": self.kind,
            "user": self.user,
            "started_at": self.started_at,
        }
        meta.update(extra)
        try:
            (self.dir / "meta.json").write_text(
                json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8"
            )
        except OSError:
            pass

    @contextmanager
    def activate(self):
        """Activate this run as the current run for the duration of the block."""
        token = _run_var.set(self)
        try:
            yield self
        finally:
            _run_var.reset(token)


def new_run(kind: str = "chat") -> RunContext:
    """Create a new run with a unique id and an initialized run directory."""
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    run_id = f"{kind}_{stamp}_{uuid.uuid4().hex[:8]}"
    directory = _home_root() / "runs" / run_id
    try:
        (directory / "logs").mkdir(parents=True, exist_ok=True)
    except OSError:
        pass
    user = "unknown"
    try:
        user = getpass.getuser()
    except Exception:
        pass
    ctx = RunContext(kind=kind, run_id=run_id, directory=directory, user=user)
    ctx.write_meta()
    return ctx


def get_current_run() -> Optional[RunContext]:
    """Return the active RunContext, or None when no run is active."""
    return _run_var.get()


def run_dir_for(run_id: str) -> Path:
    """Resolve the on-disk directory for a given run_id."""
    return _home_root() / "runs" / run_id


def log_exception(logger_name: str, message: str, *args) -> None:
    """Log an exception with full traceback.

    When a run is active the traceback is also appended to the run's
    ``logs/skill_errors.log``; otherwise it goes only to the configured logger.
    """
    import logging
    import traceback

    logger = logging.getLogger(logger_name)
    logger.exception(message, *args)

    run = get_current_run()
    if run is None:
        return
    try:
        path = run.log_path("skill_errors.log")
        path.parent.mkdir(parents=True, exist_ok=True)
        with open(path, "a", encoding="utf-8") as fh:
            try:
                rendered = message % args if args else message
            except Exception:
                rendered = message
            fh.write(f"[{_utc_now_iso()}] {rendered}\n")
            fh.write(traceback.format_exc())
            fh.write("\n")
    except OSError:
        pass
