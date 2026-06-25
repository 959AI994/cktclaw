"""
Orchestrator completion artifacts — scan deliverable files and build user-facing reports.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, asdict
from pathlib import Path
from typing import Any, Dict, List, Optional

_ARTIFACT_SUFFIXES = {
    ".sv", ".v", ".vh", ".svh", ".f", ".flist", ".tcl", ".sdc", ".xdc",
    ".json", ".md", ".txt", ".rpt", ".log", ".lib", ".lef", ".def",
}
_ARTIFACT_NAMES = {"filelist.f", "makefile"}

_WORKDIR_PATTERNS = [
    re.compile(r"(?:工作目录|working\s+dir(?:ectory)?|workdir|under)\s*[:：]?\s*([^\s\n,;]+)", re.I),
    re.compile(r"(?:under|in|at)\s+(\./[\w./-]+|\./designs/[\w./-]+|designs/[\w./-]+)", re.I),
    re.compile(r"(\./designs/[\w./-]+)", re.I),
]


@dataclass
class ArtifactEntry:
    path: str
    kind: str
    size: int

    def to_dict(self) -> dict:
        return asdict(self)


def parse_task_workdir(task: str) -> Optional[Path]:
    """Extract a project directory from the user task text."""
    if not task:
        return None
    for pattern in _WORKDIR_PATTERNS:
        m = pattern.search(task)
        if m:
            raw = m.group(1).strip().strip("'\"")
            if raw:
                return Path(raw)
    return None


def _classify_path(path: Path) -> str:
    name = path.name.lower()
    suffix = path.suffix.lower()
    if suffix in (".sv", ".svh") or name.endswith(".sv"):
        return "systemverilog"
    if suffix in (".v", ".vh"):
        return "verilog"
    if suffix == ".f" or name == "filelist.f":
        return "filelist"
    if suffix == ".sdc":
        return "constraints"
    if suffix in (".rpt", ".log"):
        return "report"
    if suffix == ".json":
        return "json"
    if suffix == ".md":
        return "markdown"
    return suffix.lstrip(".") or "file"


def _scan_directory(root: Path, *, limit: int = 80) -> List[ArtifactEntry]:
    if not root.is_dir():
        return []
    found: List[ArtifactEntry] = []
    try:
        for p in sorted(root.rglob("*"), key=lambda x: x.stat().st_mtime, reverse=True):
            if not p.is_file():
                continue
            if p.name.startswith("."):
                continue
            lower = p.name.lower()
            if p.suffix.lower() not in _ARTIFACT_SUFFIXES and lower not in _ARTIFACT_NAMES:
                continue
            try:
                size = p.stat().st_size
            except OSError:
                size = 0
            found.append(
                ArtifactEntry(
                    path=str(p.resolve()),
                    kind=_classify_path(p),
                    size=size,
                )
            )
            if len(found) >= limit:
                break
    except OSError:
        return []
    return found


def collect_artifacts(
    *,
    task: str,
    run_dir: Optional[Path] = None,
    cwd: Optional[Path] = None,
) -> List[ArtifactEntry]:
    """Collect deliverable files from task workdir, run workspace, and cwd."""
    base = cwd or Path.cwd()
    seen: set[str] = set()
    merged: List[ArtifactEntry] = []

    def _add(entries: List[ArtifactEntry]) -> None:
        for entry in entries:
            key = entry.path
            if key in seen:
                continue
            seen.add(key)
            merged.append(entry)

    workdir = parse_task_workdir(task)
    if workdir is not None:
        resolved = workdir if workdir.is_absolute() else (base / workdir)
        _add(_scan_directory(resolved.resolve()))

    if run_dir is not None:
        ws = run_dir / "workspace"
        _add(_scan_directory(ws))

    # Recent RTL-like files in cwd (shallow)
    for pattern in ("*.sv", "*.v", "filelist.f", "*.f"):
        for p in base.glob(pattern):
            if p.is_file():
                try:
                    size = p.stat().st_size
                except OSError:
                    size = 0
                _add([ArtifactEntry(path=str(p.resolve()), kind=_classify_path(p), size=size)])

    merged.sort(key=lambda e: e.path)
    return merged[:80]


def detect_qor_warnings(snapshot: dict) -> List[str]:
    """Find inconsistencies between tool-extracted QoR and stage pass status."""
    warnings: List[str] = []
    stages = snapshot.get("stages") or {}
    for stage_name, info in stages.items():
        if not isinstance(info, dict):
            continue
        status = str(info.get("status", "")).lower()
        qor = info.get("qor") or {}
        if not isinstance(qor, dict):
            continue
        if status == "passed" and qor.get("yosys_error"):
            warnings.append(
                f"阶段 `{stage_name}` 标记为通过，但 Yosys log 检测到 ERROR（yosys_error={qor.get('yosys_error')}）。"
            )
        if status == "passed" and qor.get("verilator_lint_errors"):
            n = qor.get("verilator_lint_errors")
            if isinstance(n, (int, float)) and n > 0:
                warnings.append(
                    f"阶段 `{stage_name}` 标记为通过，但 Verilator lint 报错 {n} 个。"
                )
    if snapshot.get("finished") and not stages:
        warnings.append("流程结束但未记录任何 stage 详情。")
    return warnings


def enrich_snapshot_with_artifacts(
    snapshot: dict,
    *,
    task: str,
    run_dir: Optional[Path] = None,
) -> dict:
    """Attach artifact list and paths to the orchestrator result snapshot."""
    artifacts = collect_artifacts(task=task, run_dir=run_dir)
    workdir = parse_task_workdir(task)
    out = dict(snapshot)
    out["artifacts"] = [a.to_dict() for a in artifacts]
    if workdir is not None:
        out["workdir"] = str(workdir)
    if run_dir is not None:
        out["run_dir"] = str(run_dir)
    out["warnings"] = detect_qor_warnings(snapshot)
    return out


def _format_size(size: int) -> str:
    if size < 1024:
        return f"{size} B"
    if size < 1024 * 1024:
        return f"{size / 1024:.1f} KB"
    return f"{size / (1024 * 1024):.1f} MB"


def build_completion_report(
    snapshot: dict,
    *,
    skill: str,
    task: str,
    display_name: Optional[str] = None,
) -> str:
    """Build a human-readable Markdown completion report with collapsed JSON details."""
    stages = snapshot.get("stages") or {}
    stage_order = snapshot.get("stage_order") or list(stages.keys())
    passed = sum(1 for s in stages.values() if isinstance(s, dict) and s.get("status") == "passed")
    total = len(stages) if stages else len(stage_order)
    finished = snapshot.get("finished", False)
    final_stage = snapshot.get("current_stage", "N/A")
    artifacts_raw = snapshot.get("artifacts") or []
    warnings = snapshot.get("warnings") or detect_qor_warnings(snapshot)
    workdir = snapshot.get("workdir")
    run_dir = snapshot.get("run_dir")

    title = display_name or skill
    lines: List[str] = [
        f"## Orchestrator 完成 — {title}",
        "",
    ]

    if finished and passed == total and total > 0:
        lines.append(f"**结果：** {passed}/{total} 个阶段已通过，最终阶段 `{final_stage}`。")
    elif total > 0:
        lines.append(f"**结果：** {passed}/{total} 个阶段通过（finished={finished}，当前 `{final_stage}`）。")
    else:
        lines.append(f"**结果：** 流程已结束（finished={finished}）。")

    lines.append("")
    lines.append("**各阶段：**")
    for name in stage_order:
        info = stages.get(name) if isinstance(stages, dict) else None
        if not isinstance(info, dict):
            lines.append(f"- `{name}` — （无记录）")
            continue
        st = info.get("status", "?")
        attempts = info.get("attempts", 1)
        lines.append(f"- `{name}` — **{st}**（尝试 {attempts} 次）")

    if workdir:
        lines.extend(["", f"**任务目录：** `{workdir}`"])
    if run_dir:
        lines.append(f"**Run 目录：** `{run_dir}`")

    lines.extend(["", "**产物文件：**"])
    if artifacts_raw:
        for item in artifacts_raw:
            if isinstance(item, dict):
                path = item.get("path", "?")
                kind = item.get("kind", "file")
                size = item.get("size", 0)
                lines.append(f"- `{path}` ({kind}, {_format_size(int(size or 0))})")
            else:
                lines.append(f"- `{item}`")
    else:
        lines.append(
            "- 未在任务目录或 run workspace 中发现 `.sv` / `.v` / `filelist.f` 等产物。"
        )
        lines.append(
            "- 可能仅完成了规划与指标自报，LLM 未实际 Write 文件到磁盘；请检查 Chat 日志中的工具调用。"
        )

    if warnings:
        lines.extend(["", "**⚠️ 注意事项：**"])
        for w in warnings:
            lines.append(f"- {w}")

    lines.extend([
        "",
        "**说明：** QoR 指标来自各 stage 的 LLM 自报与 Yosys/Verilator 等工具 log 解析，",
        "不等同于 sign-off 审计结论；请以产物文件与报告为准。",
        "",
        "### 技术详情 (JSON)",
        "",
        "```json",
        json.dumps(
            {k: v for k, v in snapshot.items() if k != "artifacts"},
            indent=2,
            ensure_ascii=False,
            default=str,
        ),
        "```",
    ])

    return "\n".join(lines)
