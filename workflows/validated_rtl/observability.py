"""CLI helpers for ValidatedRTL LLM workflow trace."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, Iterable, Optional


def _trace_candidates(project_dir: Path) -> Iterable[Path]:
    root = project_dir.resolve()
    yield root / "reports" / "workflow_trace.json"
    yield root / "eda_validated_rtl" / "reports" / "workflow_trace.json"
    yield root / "eda_autodesign" / "eda_validated_rtl" / "reports" / "workflow_trace.json"


def load_workflow_trace(project_dir: str | Path | None) -> Optional[Dict[str, Any]]:
    if not project_dir:
        return None
    for path in _trace_candidates(Path(project_dir)):
        if path.is_file():
            try:
                return json.loads(path.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError):
                return None
    return None


def format_rtl_llm_cli_summary(
    project_dir: str | Path | None,
    *,
    overall_status: str = "",
) -> str:
    trace = load_workflow_trace(project_dir)
    if trace is None:
        if overall_status.upper() == "FAIL":
            return "RTL LLM: not reached (no workflow_trace.json)"
        return ""

    provider = trace.get("rtl_llm_provider") or "unknown"
    called = trace.get("rtl_llm_called")
    status = str(trace.get("rtl_llm_status") or "unknown")
    error = str(trace.get("workflow_error") or trace.get("error") or "").strip()
    generation_mode = str(trace.get("generation_mode") or "workflow")

    if status.startswith("constraint_failed:"):
        detail = status.split(":", 1)[1].strip()
        mode_note = f"; mode={generation_mode}" if generation_mode else ""
        return f"RTL LLM: constraint failed ({detail}){mode_note}"

    if status.startswith("salvage_failed:"):
        detail = status.split(":", 1)[1].strip()
        mode_note = f"; mode={generation_mode}" if generation_mode else ""
        return f"RTL LLM: salvage failed ({detail}){mode_note}"

    if trace.get("materialization_failed") and overall_status.upper() == "FAIL":
        mode_note = f"; mode={generation_mode}" if generation_mode else ""
        detail = error or status
        return f"RTL LLM: materialization failed ({detail}){mode_note}"

    if status in {"salvage_extract", "direct_llm_fallback", "workflow_salvaged"}:
        return f"RTL LLM: {status} (mode={generation_mode})"

    if status.startswith("workflow_failed:"):
        detail = status.split(":", 1)[1].strip()
        return f"RTL LLM: failed ({detail})"

    if status in {"adapter_load_failed", "adapter_bind_failed", "not_reached", "not_started"}:
        detail = error or status.replace("_", " ")
        return f"RTL LLM: not reached ({detail})"

    if called is True and status == "completed":
        if overall_status.upper() == "FAIL" and (
            error
            or trace.get("materialization_failed")
            or generation_mode in {"salvage", "salvage_extract", "workflow_salvaged"}
        ):
            mode_note = f"; mode={generation_mode}" if generation_mode else ""
            detail = error or "workflow constraint or materialization failed"
            return f"RTL LLM: {provider} called but EDA failed ({detail}){mode_note}"
        bridge = "cktclaw_llm_bridge" if provider == "command" else provider
        return f"RTL LLM: {provider} via {bridge} (called)"

    if called is True:
        return f"RTL LLM: {provider} (status={status})"

    return f"RTL LLM: {provider} (not called; status={status})"


def append_llm_trace_section(lines: list[str], project_dir: str | Path | None, *, overall_status: str = "") -> None:
    summary = format_rtl_llm_cli_summary(project_dir, overall_status=overall_status)
    if not summary:
        return
    trace = load_workflow_trace(project_dir)
    lines.extend(["", "### LLM Trace", "", f"- {summary}"])
    if trace:
        for key in (
            "execution_stack",
            "rtl_llm_provider",
            "rtl_llm_called",
            "rtl_llm_status",
            "generation_mode",
            "workflow_error",
            "error",
        ):
            if key in trace and trace[key] not in (None, "", False):
                lines.append(f"- `{key}`: `{trace[key]}`")
