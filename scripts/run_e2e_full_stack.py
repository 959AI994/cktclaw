#!/usr/bin/env python3
"""
CktClaw full-stack E2E runner (CLI path).

Phases:
  preflight   — doctor + pytest baseline (also: scripts/run_e2e_preflight.sh)
  fixtures    — deploy tests/fixtures/full_chip_e2e/workspace → workspace/
  toolchain   — Prompt 10 direct tool smoke → tests/e2e_reports/10_toolchain.md
  skills      — Prompts 1-6 (LLM chat or skill-bridge fallback)
  eda         — Prompts 7-8 (/chip-system --eda-only)
  full        — Prompt 9 (seven-agent full pipeline)
  all         — run everything in order

Usage:
  source activate.sh
  python scripts/run_e2e_full_stack.py all
  python scripts/run_e2e_full_stack.py toolchain
"""
from __future__ import annotations

import asyncio
import json
import os
import re
import shlex
import shutil
import subprocess
import sys
import time
import uuid
from dataclasses import dataclass, field
from datetime import datetime
from io import StringIO
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

_ROOT = Path(__file__).resolve().parent.parent
if str(_ROOT.parent) not in sys.path:
    sys.path.insert(0, str(_ROOT.parent))

REPORT_DIR = _ROOT / "tests" / "e2e_reports"
FIXTURE_ROOT = _ROOT / "tests" / "fixtures" / "full_chip_e2e" / "workspace"
WORKSPACE = _ROOT / "workspace"
RUNS_SAT = _ROOT / "runs" / "sat_accum"


PROMPTS: Dict[int, str] = {
    1: (
        "请设计一个 8-bit pipelined adder，要求 Verilog-2001，可综合，带 valid/ready 接口，"
        "并生成 self-checking testbench。请使用 verilog-generator 的流程，"
        "最后说明生成了哪些文件以及如何验证。"
    ),
    2: (
        "请使用 RTLRepairAgent 修复 workspace/bad_counter.v。目标行为是：同步复位，"
        "高电平 reset 时 count 清零，否则每个时钟 +1。请先用 verible/slang/verilator "
        "能用的工具复现错误，再给出最小修复，并说明验证证据。"
    ),
    3: (
        "请为一个 4-bit up counter 写形式验证计划和 SymbiYosys .sby 文件：reset 后 count 为 0，"
        "之后每拍递增，溢出回到 0。请使用 FormalAgent，并说明 assumptions、assertions、"
        "cover property 和如何运行 sby。"
    ),
    4: (
        "请使用 HLSAgent/hls-generator 设计一个 streaming FIR filter，输入输出都是 AXI4-Stream，"
        "16-bit data，8 taps。请生成 C++ kernel、testbench、Vitis HLS Tcl，"
        "并解释 PIPELINE、ARRAY_PARTITION、接口 pragma 的选择。"
    ),
    5: (
        "请使用 AnalogAgent 设计一个两级 CMOS OTA 的完整模拟设计流程。目标：低频增益 > 60 dB，"
        "UGB > 20 MHz，相位裕度 > 60 度，负载 2 pF。请输出架构选择、block budget、"
        "SPICE testbench、PVT/Monte Carlo 验证矩阵、layout-sensitive constraints。"
    ),
    6: (
        "请使用 PPAOptimizerAgent 分析一个 RTL 设计的 PPA 优化策略。假设当前 Yosys/OpenSTA "
        "报告显示 area 偏大且 WNS=-0.35ns。请给出可能的 RTL-level、constraint-level、"
        "synthesis-flow-level 优化候选，并设计验证/回归 gate。"
    ),
    7: (
        "/chip-system 设计一个 8-bit saturating accumulator，从需求到 RTL、验证、综合、"
        "STA、PPA 优化都跑一遍。目标是面积优先，允许一拍 latency，"
        "workdir ./runs/sat_accum --eda-only"
    ),
    8: (
        "/chip-system 请修复并完成 ./workspace/broken_fifo.v 的 RTL 到验证到综合闭环。"
        "这个 FIFO 现在 testbench 会失败，请不要跳过失败；如果 RTL/verification/synthesis "
        "失败，请派发 RTLRepairAgent 或 PPAOptimizerAgent 给出修复建议。--eda-only"
    ),
    9: (
        "/chip-system 设计一个小型 streaming packet checksum accelerator，包括硬件 RTL、"
        "软件 driver、runtime 调度、FPGA bring-up plan 和 PPA 优化计划。"
        "目标吞吐 1 byte/cycle，workdir ./runs/checksum_accel"
    ),
}

TOOLCHAIN_PROMPTS = [
    "请用 verible lint 检查 ./workspace/top.sv，并总结所有 style/syntax 问题。",
    "请用 slang 编译检查 ./workspace/top.sv，top module 是 top，包含目录是 ./workspace/include。",
    "请用 verilator --lint-only 检查 ./workspace/top.sv，并解释每个 warning 是否需要修。",
    "请为 ./workspace/top.sv 写一个最小 SymbiYosys prove job，并尝试运行 sby。",
]

SKILL_HINTS: Dict[int, List[str]] = {
    1: ["erie-verilog-generator", "verilog-generator", "verilog_generator"],
    2: ["rtl-repair", "rtl_repair", "RTLRepair"],
    3: ["formal", "formal_agent", "chip-formal", "sby"],
    4: ["hls-generator", "hls_generator", "HLSAgent"],
    5: ["analog", "analog-design", "AnalogAgent"],
    6: ["ppa_optimizer", "PPAOptimizer", "optimizer"],
    7: ["chip-system", "eda_agent", "chip-rtl", "chip-verification"],
    8: ["chip-system", "fix_request", "rtl_repair_agent", "specialist_dispatched"],
    9: ["chip-system", "pm_agent", "architect_agent", "deploy_agent", "optimizer_agent"],
}


@dataclass
class PromptReport:
    prompt_id: int
    skill_agent_hits: List[str] = field(default_factory=list)
    tool_commands: List[str] = field(default_factory=list)
    artifacts: List[str] = field(default_factory=list)
    design_state_changes: str = ""
    verdict: str = "FAIL"  # PASS | PARTIAL | FAIL | BLOCKED | SKIPPED
    notes: str = ""
    raw_output: str = ""


def _ensure_dirs() -> None:
    REPORT_DIR.mkdir(parents=True, exist_ok=True)
    WORKSPACE.mkdir(parents=True, exist_ok=True)
    RUNS_SAT.mkdir(parents=True, exist_ok=True)


def deploy_fixtures() -> None:
    """Copy fixture RTL into workspace/."""
    _ensure_dirs()
    for src in FIXTURE_ROOT.rglob("*"):
        if src.is_file():
            rel = src.relative_to(FIXTURE_ROOT)
            dst = WORKSPACE / rel
            dst.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(src, dst)
    print(f"Deployed fixtures → {WORKSPACE}")


def _run_cmd(cmd: List[str], cwd: Optional[Path] = None, timeout: int = 120) -> Dict[str, Any]:
    t0 = time.perf_counter()
    try:
        proc = subprocess.run(
            cmd,
            cwd=str(cwd or _ROOT),
            capture_output=True,
            text=True,
            timeout=timeout,
        )
        return {
            "cmd": " ".join(shlex.quote(c) for c in cmd),
            "exit_code": proc.returncode,
            "stdout": proc.stdout[-8000:],
            "stderr": proc.stderr[-8000:],
            "seconds": round(time.perf_counter() - t0, 2),
        }
    except FileNotFoundError:
        return {
            "cmd": " ".join(shlex.quote(c) for c in cmd),
            "exit_code": -1,
            "stdout": "",
            "stderr": "executable not found on PATH",
            "seconds": round(time.perf_counter() - t0, 2),
        }
    except subprocess.TimeoutExpired:
        return {
            "cmd": " ".join(shlex.quote(c) for c in cmd),
            "exit_code": -2,
            "stdout": "",
            "stderr": f"timeout after {timeout}s",
            "seconds": timeout,
        }


def run_toolchain_smoke() -> PromptReport:
    """Phase 1 — direct EDA binary smoke (Prompt 10)."""
    deploy_fixtures()
    top = WORKSPACE / "top.sv"
    include = WORKSPACE / "include"
    results: List[Dict[str, Any]] = []

    checks = [
        ("verible-verilog-lint", [shutil.which("verible-verilog-lint") or "verible-verilog-lint",
                                  str(top)]),
        ("slang", [shutil.which("slang") or "slang",
                   str(top), "--top", "top", "-I", str(include)]),
        ("verilator", [shutil.which("verilator") or "verilator",
                       "--lint-only", "-Wall", f"-I{include}", str(top)]),
    ]
    for name, cmd in checks:
        results.append({"tool": name, **_run_cmd(cmd)})

    # Minimal SymbiYosys job
    sby_dir = _ROOT / "runs" / "e2e_sby_smoke"
    sby_dir.mkdir(parents=True, exist_ok=True)
    sby_file = sby_dir / "smoke.sby"
    sby_file.write_text(
        f"""[options]
mode prove
depth 10

[engines]
smtbmc

[script]
read -formal {top.resolve()}
prep -top top

[files]
{top.resolve()}
{(include / 'defs.svh').resolve()}
""",
        encoding="utf-8",
    )
    sby_cmd = [shutil.which("sby") or "sby", "-f", str(sby_file)]
    results.append({"tool": "symbiyosys", **_run_cmd(sby_cmd, cwd=sby_dir, timeout=180)})

    hits = [r["tool"] for r in results if r.get("exit_code", 1) == 0]
    missing = [r["tool"] for r in results if r.get("exit_code") == -1]
    failed = [r["tool"] for r in results if r.get("exit_code", 1) not in (0, -1)]

    if len(hits) >= 2 and not failed:
        verdict = "PASS"
    elif hits:
        verdict = "PARTIAL"
    else:
        verdict = "PARTIAL" if missing else "FAIL"

    notes = []
    if missing:
        notes.append(f"skipped_tool: {', '.join(missing)}")
    if failed:
        notes.append(f"failed_run: {', '.join(failed)}")

    report = PromptReport(
        prompt_id=10,
        skill_agent_hits=["tool_smoke_direct"],
        tool_commands=[r["cmd"] for r in results],
        artifacts=[str(sby_file)],
        verdict=verdict,
        notes="; ".join(notes),
        raw_output=json.dumps(results, indent=2, ensure_ascii=False),
    )
    _write_report(report, "10_toolchain.md")
    return report


def _write_report(report: PromptReport, filename: str) -> Path:
    path = REPORT_DIR / filename
    body = f"""## Prompt {report.prompt_id}
- Skill/Agent 命中: {', '.join(report.skill_agent_hits) or 'none'}
- 工具命令: 
{chr(10).join('  - `' + c + '`' for c in report.tool_commands) or '  - none'}
- Artifacts: {', '.join(report.artifacts) or 'none'}
- design_state 变化: {report.design_state_changes or 'none'}
- 结论: {report.verdict}
- 备注: {report.notes}

<details>
<summary>Raw output</summary>

```
{report.raw_output[:12000]}
```
</details>
"""
    path.write_text(body, encoding="utf-8")
    print(f"Wrote {path}")
    return path


def _llm_available() -> Tuple[bool, str]:
    try:
        from cktclaw.llm import get_model_router
        router = get_model_router()
        router.initialize()
        if router.available_providers:
            return True, router.current_name
        return False, "none"
    except Exception as exc:
        return False, str(exc)


def _scan_hits(text: str, hints: List[str]) -> List[str]:
    lower = text.lower()
    return [h for h in hints if h.lower() in lower]


def _read_design_state_summary() -> str:
    candidates = [
        _ROOT / "design_state.json",
        Path.home() / ".cktclaw" / "design_state.json",
    ]
    for p in candidates:
        if p.is_file():
            try:
                data = json.loads(p.read_text(encoding="utf-8"))
                keys = list(data.keys())[:20]
                fix = data.get("fix_requests", [])
                return f"path={p}; keys={keys}; fix_requests={len(fix)} open"
            except Exception:
                return f"path={p}; parse_error"
    return "design_state.json not found"


async def _run_chat_prompt(prompt: str, session_suffix: str) -> Tuple[str, str]:
    """Run process_chat_v3 and capture console output."""
    from rich.console import Console
    from cktclaw.main import CLIState
    from cktclaw.handlers.chat_handler_v3 import process_chat_v3

    buf = StringIO()
    console = Console(file=buf, width=120, record=True, force_terminal=False)
    cli = CLIState()
    cli.console = console
    cli.session_id = f"e2e_{session_suffix}_{uuid.uuid4().hex[:8]}"
    cli.current_engine = "deepseek"

    await process_chat_v3(prompt, cli)
    try:
        text = console.export_text(clear=False)
    except Exception:
        text = buf.getvalue()
    return text, cli.session_id


def _bootstrap_skills() -> None:
    """Register bundled skills (mirrors main.py startup)."""
    asyncio.run(_ensure_skills_registered())


_SKILLS_REGISTERED = False


async def _ensure_skills_registered() -> None:
    global _SKILLS_REGISTERED
    if _SKILLS_REGISTERED:
        return
    from cktclaw.skills import (
        register_chip_design_skills,
        register_analog_design_skills,
        register_rtl_repair_skill,
        register_verilog_generator_skill,
        register_hls_generator_skill,
        register_external_skills,
    )
    from cktclaw.skills.chip_system_skill import register_chip_system_skill

    await register_chip_design_skills()
    await register_analog_design_skills()
    await register_rtl_repair_skill()
    await register_verilog_generator_skill()
    await register_hls_generator_skill()
    await register_chip_system_skill()
    await register_external_skills(verbose=False)
    _SKILLS_REGISTERED = True


async def _run_skill_bridge(prompt_id: int, prompt: str) -> PromptReport:
    """Fallback when LLM unavailable — route + invoke mapped skills directly."""
    await _ensure_skills_registered()
    from cktclaw.handlers.intent_router import detect_chip_design_intent_with_confidence
    from cktclaw.capability_registry import get_capability_registry

    route = detect_chip_design_intent_with_confidence(prompt)
    hits: List[str] = []
    if route:
        hits.append(route["skill_id"])

    cap = get_capability_registry()
    outputs: List[str] = []
    skill_map = {
        1: "erie-verilog-generator",
        2: "rtl-repair",
        3: "chip-formal",
        4: "chip-hls",
        5: "analog-design-architecture",
        6: "chip-synthesis",
    }
    skill_name = skill_map.get(prompt_id)
    entry = await cap.get(skill_name) if skill_name else None
    if skill_name and entry:
        try:
            result = await cap.execute(skill_name, {"args": prompt}, {"cli_state": None})
            text = _result_to_text(result)
            outputs.append(text)
            hits.append(skill_name)
        except Exception as exc:
            outputs.append(f"Skill {skill_name} error: {exc}")

    if prompt_id == 2:
        bad = WORKSPACE / "bad_counter.v"
        verilator = shutil.which("verilator")
        if bad.is_file() and verilator:
            lint = _run_cmd([verilator, "--lint-only", "-Wall", str(bad)])
            outputs.append(
                f"## Verilator reproduce (bad_counter.v)\n"
                f"cmd: {lint['cmd']}\nexit: {lint['exit_code']}\n{lint['stderr'][:2000]}"
            )

    combined = "\n\n".join(outputs)
    scanned = _scan_hits(combined, SKILL_HINTS.get(prompt_id, []))
    hits.extend(scanned)
    hits = list(dict.fromkeys(hits))

    verdict = "PARTIAL" if hits else "BLOCKED"
    tool_cmds = []
    if prompt_id == 2:
        tool_cmds = re.findall(r"cmd: ([^\n]+)", combined)
    return PromptReport(
        prompt_id=prompt_id,
        skill_agent_hits=hits,
        tool_commands=tool_cmds,
        artifacts=[],
        design_state_changes=_read_design_state_summary(),
        verdict=verdict,
        notes="LLM unavailable — skill-bridge fallback only",
        raw_output=combined or f"route={route}",
    )


def _result_to_text(result: Any) -> str:
    if isinstance(result, list):
        parts = []
        for item in result:
            if isinstance(item, dict) and "text" in item:
                parts.append(str(item["text"]))
            else:
                parts.append(str(item))
        return "\n\n".join(parts)
    return str(result) if result is not None else ""


async def _run_prompt_chat(prompt_id: int) -> PromptReport:
    prompt = PROMPTS[prompt_id]
    llm_ok, provider = _llm_available()

    if not llm_ok:
        return await _run_skill_bridge(prompt_id, prompt)

    t0 = time.perf_counter()
    try:
        raw, session_id = await _run_chat_prompt(prompt, f"p{prompt_id}")
    except Exception as exc:
        rep = await _run_skill_bridge(prompt_id, prompt)
        rep.notes = f"LLM call failed ({exc}); fallback to skill-bridge"
        rep.verdict = "PARTIAL"
        return rep

    hits = _scan_hits(raw, SKILL_HINTS.get(prompt_id, []))
    route_hit = None
    if prompt_id <= 6:
        from cktclaw.handlers.intent_router import detect_chip_design_intent
        route_hit = detect_chip_design_intent(prompt)
        if route_hit:
            hits.insert(0, route_hit)

    tool_cmds = re.findall(
        r"(verilator|yosys|sby|verible|slang|sta|abc)[^\n`]*",
        raw,
        re.IGNORECASE,
    )

    verdict = "PASS" if len(hits) >= 2 else ("PARTIAL" if hits else "FAIL")
    if prompt_id == 2 and "repair" in raw.lower():
        verdict = "PASS" if verdict != "FAIL" else "PARTIAL"

    return PromptReport(
        prompt_id=prompt_id,
        skill_agent_hits=list(dict.fromkeys(hits)),
        tool_commands=tool_cmds[:10],
        artifacts=_find_recent_artifacts(),
        design_state_changes=_read_design_state_summary(),
        verdict=verdict,
        notes=f"provider={provider}; session={session_id}; elapsed={round(time.perf_counter()-t0,1)}s",
        raw_output=raw,
    )


async def _run_chip_system(prompt_id: int) -> PromptReport:
    await _ensure_skills_registered()
    from cktclaw.main import CLIState
    from cktclaw.skills.chip_system_skill import chip_system_executor, _parse_args

    prompt = PROMPTS[prompt_id]
    args_text = prompt
    if args_text.startswith("/chip-system"):
        args_text = args_text[len("/chip-system"):].strip()
    goal, mode = _parse_args(args_text)

    cli = CLIState()
    llm_ok, provider = _llm_available()
    t0 = time.perf_counter()

    try:
        result = await chip_system_executor(prompt, {"cli_state": cli})
        raw = _result_to_text(result)
        if isinstance(result, list) and len(result) > 1:
            ma = result[1].get("result", {}) if isinstance(result[1], dict) else {}
            raw += "\n\n" + json.dumps(ma, indent=2, ensure_ascii=False)[:8000]
    except Exception as exc:
        raw = f"chip_system_executor failed: {exc}"

    hits = _scan_hits(raw, SKILL_HINTS.get(prompt_id, []))
    ds = _read_design_state_summary()

    # Prompt 8 specific checks
    extra_notes = []
    if prompt_id == 8:
        ds_path = Path.home() / ".cktclaw" / "design_state.json"
        if not ds_path.is_file():
            ds_path = _ROOT / "design_state.json"
        if ds_path.is_file():
            data = json.loads(ds_path.read_text(encoding="utf-8"))
            fix_reqs = data.get("fix_requests", [])
            open_reqs = [f for f in fix_reqs if f.get("status") == "open"]
            if open_reqs:
                hits.append("fix_requests_open")
                extra_notes.append(f"open fix_requests={len(open_reqs)}")
            if "specialist_dispatched" in raw:
                hits.append("specialist_dispatched")

    if prompt_id == 7:
        for stage in ["chip-rtl", "chip-verification", "chip-synthesis", "chip-sta"]:
            if stage in raw:
                hits.append(stage)

    if not llm_ok:
        if "eda_agent" in raw and "completed" in raw.lower():
            verdict = "PARTIAL"
        else:
            verdict = "BLOCKED"
        extra_notes.append("LLM unavailable — re-run with DEEPSEEK_API_KEY for full DeepSeek E2E")
    else:
        verdict = "PASS" if "completed" in raw.lower() and len(hits) >= 3 else "PARTIAL"

    return PromptReport(
        prompt_id=prompt_id,
        skill_agent_hits=list(dict.fromkeys(hits)),
        tool_commands=re.findall(r"chip-\w+", raw)[:15],
        artifacts=_find_recent_artifacts() + _list_run_artifacts(),
        design_state_changes=ds,
        verdict=verdict,
        notes=f"provider={provider}; mode={mode}; {'; '.join(extra_notes)}; elapsed={round(time.perf_counter()-t0,1)}s",
        raw_output=raw,
    )


def _find_recent_artifacts() -> List[str]:
    paths: List[str] = []
    for base in [_ROOT / "artifacts", _ROOT / "runs", _ROOT / ".cktclaw" / "runs"]:
        if not base.exists():
            continue
        for p in sorted(base.rglob("*"), key=lambda x: x.stat().st_mtime, reverse=True)[:15]:
            if p.is_file():
                paths.append(str(p.relative_to(_ROOT)))
    return paths[:10]


def _list_run_artifacts() -> List[str]:
    out: List[str] = []
    for d in [RUNS_SAT, _ROOT / "runs" / "checksum_accel"]:
        if d.exists():
            for p in d.rglob("*"):
                if p.is_file():
                    out.append(str(p.relative_to(_ROOT)))
    return out[:15]


async def run_skills_phase() -> List[PromptReport]:
    reports = []
    for pid in range(1, 7):
        print(f"\n==> Prompt {pid}")
        rep = await _run_prompt_chat(pid)
        _write_report(rep, f"0{pid}_{_prompt_slug(pid)}.md")
        reports.append(rep)
    return reports


def _prompt_slug(pid: int) -> str:
    return {
        1: "verilog_gen",
        2: "rtl_repair",
        3: "formal",
        4: "hls",
        5: "analog",
        6: "ppa",
        7: "eda_only",
        8: "failure_dispatch",
        9: "full_seven_agent",
    }.get(pid, f"prompt_{pid}")


async def run_eda_phase() -> List[PromptReport]:
    deploy_fixtures()
    reports = []
    for pid in (7, 8):
        print(f"\n==> Prompt {pid} (/chip-system)")
        rep = await _run_chip_system(pid)
        _write_report(rep, f"0{pid}_{_prompt_slug(pid)}.md")
        reports.append(rep)
    return reports


async def run_full_pipeline() -> PromptReport:
    deploy_fixtures()
    log_path = REPORT_DIR / "09_full_chip_system.log"
    print(f"\n==> Prompt 9 (logging to {log_path})")

    rep = await _run_chip_system(9)
    log_path.write_text(rep.raw_output, encoding="utf-8")
    _write_report(rep, "09_full_seven_agent.md")
    return rep


def write_summary(reports: List[PromptReport]) -> None:
    path = REPORT_DIR / f"{datetime.now():%Y%m%d}_summary.md"
    lines = ["# CktClaw E2E Summary", "", f"Generated: {datetime.now().isoformat()}", ""]
    lines.append("| ID | Verdict | Hits | Notes |")
    lines.append("|----|---------|------|-------|")
    for r in sorted(reports, key=lambda x: x.prompt_id):
        lines.append(
            f"| {r.prompt_id} | {r.verdict} | {', '.join(r.skill_agent_hits[:3])} | {r.notes[:80]} |"
        )
    path.write_text("\n".join(lines), encoding="utf-8")
    print(f"Wrote {path}")


async def main_async(phase: str) -> int:
    _ensure_dirs()
    reports: List[PromptReport] = []

    if phase in ("skills", "eda", "full", "all"):
        await _ensure_skills_registered()

    if phase in ("preflight", "all"):
        script = _ROOT / "scripts" / "run_e2e_preflight.sh"
        rc = subprocess.call(["bash", str(script)])
        if rc != 0 and phase == "preflight":
            return rc

    if phase in ("fixtures", "all"):
        deploy_fixtures()

    if phase in ("toolchain", "all"):
        reports.append(run_toolchain_smoke())

    if phase in ("skills", "all"):
        deploy_fixtures()
        reports.extend(await run_skills_phase())

    if phase in ("eda", "all"):
        reports.extend(await run_eda_phase())

    if phase in ("full", "all"):
        reports.append(await run_full_pipeline())

    if reports:
        write_summary(reports)

    blocked = [r for r in reports if r.verdict == "BLOCKED"]
    if blocked and not _llm_available()[0]:
        print("\n⚠ Some prompts BLOCKED — set DEEPSEEK_API_KEY in .env and re-run skills/eda/full phases.")
    return 0


def main() -> None:
    phase = sys.argv[1] if len(sys.argv) > 1 else "all"
    valid = {"preflight", "fixtures", "toolchain", "skills", "eda", "full", "all"}
    if phase not in valid:
        print(f"Unknown phase {phase!r}. Valid: {', '.join(sorted(valid))}")
        sys.exit(2)
    os.chdir(_ROOT)
    rc = asyncio.run(main_async(phase))
    sys.exit(rc)


if __name__ == "__main__":
    main()
