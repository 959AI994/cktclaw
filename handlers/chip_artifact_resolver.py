"""Read-only artifact resolver for chip mission follow-up questions."""

from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, Iterable, Optional

from .schemas import ArtifactQuery


def resolve_chip_artifact_query(
    query: Optional[ArtifactQuery],
    *,
    context: Optional[Dict[str, Any]] = None,
    cli_state: Any = None,
) -> ArtifactQuery:
    """Resolve latest chip mission artifacts without executing any tools."""
    context = context or {}
    query = query or ArtifactQuery(kind="unknown")

    last_mission_id = query.last_chip_mission_id or _context_value(
        context, cli_state, "last_chip_mission_id"
    )
    last_project_dir = query.last_project_dir or _context_value(
        context, cli_state, "last_project_dir"
    )

    candidates: list[Path] = [Path(p).expanduser() for p in query.candidate_paths]
    candidates.extend(_paths_from_context(context, cli_state))

    state = _load_design_state()
    mission = state.get("mission", {}) if isinstance(state, dict) else {}
    if isinstance(mission, dict):
        if not last_mission_id:
            last_mission_id = mission.get("last_chip_mission_id") or _mission_id_from_spec(mission)
        if not last_project_dir:
            last_project_dir = mission.get("last_project_dir")
        idx = mission.get("artifacts_index") or {}
        if isinstance(idx, dict):
            candidates.extend(Path(v).expanduser() for v in idx.values() if _is_pathlike(v))
        for phase in mission.get("phases") or []:
            if isinstance(phase, dict):
                candidates.extend(Path(v).expanduser() for v in phase.get("artifacts") or [] if _is_pathlike(v))

    if last_project_dir:
        candidates.extend(_project_artifacts(Path(last_project_dir).expanduser()))
    if not context.get("disable_fallback_scan"):
        candidates.extend(_latest_run_artifacts())

    resolved = _select_artifacts(query.kind, candidates)
    missing = _missing_for_kind(query.kind, resolved)
    return ArtifactQuery(
        kind=query.kind,
        last_chip_mission_id=last_mission_id,
        last_project_dir=last_project_dir,
        candidate_paths=_dedupe_str(candidates),
        resolved_paths=_dedupe_str(resolved),
        missing_artifacts=missing,
    )


def render_artifact_query_for_cli(query: ArtifactQuery) -> str:
    """Return a compact terminal/web-friendly artifact preview."""
    if not query.resolved_paths:
        missing = ", ".join(query.missing_artifacts or [query.kind])
        return f"Artifact missing: {missing}\n请提供 DUT RTL 路径，或选择上一轮 mission 的 RTL artifact。"

    parts: list[str] = []
    for path_text in query.resolved_paths:
        path = Path(path_text)
        parts.append(f"Path: {path}")
        if not path.is_file():
            parts.append("(missing on disk)")
            continue
        if path.name == "simulation.log":
            lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
            body = "\n".join(lines[-120:])
            parts.append("```text\n" + body + "\n```")
        elif path.suffix.lower() in {".sv", ".v", ".vh", ".svh"}:
            lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
            body = "\n".join(f"{idx + 1:4d}: {line}" for idx, line in enumerate(lines[:200]))
            parts.append("```systemverilog\n" + body + "\n```")
        else:
            lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
            body = "\n".join(lines[:160])
            parts.append("```markdown\n" + body + "\n```")
    return "\n\n".join(parts)


def latest_resolved_rtl(context: Optional[Dict[str, Any]] = None, cli_state: Any = None) -> Optional[str]:
    query = resolve_chip_artifact_query(ArtifactQuery(kind="rtl"), context=context, cli_state=cli_state)
    return query.resolved_paths[0] if query.resolved_paths else None


def _context_value(context: Dict[str, Any], cli_state: Any, key: str) -> Optional[str]:
    val = context.get(key)
    if val:
        return str(val)
    if cli_state is not None and getattr(cli_state, key, None):
        return str(getattr(cli_state, key))
    return None


def _paths_from_context(context: Dict[str, Any], cli_state: Any) -> list[Path]:
    paths: list[Path] = []
    for key in ("rtl_path", "dut_path", "simulation_log", "report_path"):
        val = _context_value(context, cli_state, key)
        if val:
            paths.append(Path(val).expanduser())
    return paths


def _load_design_state() -> dict:
    try:
        from ..orchestrator.design_state import DesignStateStore
        store = DesignStateStore()
        return store.load()
    except Exception:
        return {}


def _mission_id_from_spec(mission: dict) -> Optional[str]:
    spec = mission.get("mission_spec")
    if isinstance(spec, dict) and spec.get("mission_id"):
        return str(spec["mission_id"])
    return None


def _is_pathlike(value: Any) -> bool:
    return isinstance(value, str) and ("/" in value or value.endswith((".sv", ".v", ".log", ".md")))


def _project_artifacts(project_dir: Path) -> list[Path]:
    roots = [project_dir]
    if (project_dir / "eda_autodesign").exists():
        roots.insert(0, project_dir / "eda_autodesign")
    results: list[Path] = []
    for root in roots:
        results.extend(_glob_artifacts(root))
    return results


def _latest_run_artifacts() -> list[Path]:
    roots = [
        Path.cwd() / "runs" / "chip_mission",
        Path.cwd().parent / "runs" / "chip_mission",
        Path("/home/wjx/pythonproject/runs/chip_mission"),
    ]
    runs: list[Path] = []
    for root in roots:
        if root.is_dir():
            runs.extend(p for p in root.iterdir() if p.is_dir())
    runs = sorted(set(runs), key=lambda p: p.stat().st_mtime if p.exists() else 0, reverse=True)
    results: list[Path] = []
    for run in runs[:8]:
        auto = run / "eda_autodesign"
        results.extend(_glob_artifacts(auto if auto.exists() else run))
    return results


def _glob_artifacts(root: Path) -> list[Path]:
    if not root.exists():
        return []
    results: list[Path] = []
    results.extend(sorted((root / "rtl").glob("*.sv")))
    results.extend(sorted((root / "rtl").glob("*.v")))
    sim = root / "reports" / "simulation.log"
    if sim.exists():
        results.append(sim)
    results.extend(sorted((root / "reports").glob("*report*.md")) if (root / "reports").exists() else [])
    return results


def _select_artifacts(kind: str, candidates: Iterable[Path]) -> list[Path]:
    existing = [p for p in candidates if p.is_file()]
    rtl = [p for p in existing if p.suffix.lower() in {".sv", ".v"} and "/rtl/" in str(p)]
    sim = [p for p in existing if p.name == "simulation.log"]
    reports = [p for p in existing if p.suffix.lower() == ".md" and "report" in p.name.lower()]
    if kind in {"rtl", "code"}:
        return rtl[:1]
    if kind == "simulation_log":
        return sim[:1]
    if kind == "report":
        return reports[:1]
    selected: list[Path] = []
    selected.extend(rtl[:1])
    selected.extend(sim[:1])
    selected.extend(reports[:1])
    return selected


def _missing_for_kind(kind: str, resolved: list[Path]) -> list[str]:
    if resolved:
        return []
    if kind in {"rtl", "code"}:
        return ["rtl"]
    if kind == "simulation_log":
        return ["simulation_log"]
    if kind == "report":
        return ["report"]
    return ["rtl", "simulation_log"]


def _dedupe_str(paths: Iterable[Path]) -> list[str]:
    seen: set[str] = set()
    out: list[str] = []
    for path in paths:
        text = str(path)
        if text not in seen:
            seen.add(text)
            out.append(text)
    return out
