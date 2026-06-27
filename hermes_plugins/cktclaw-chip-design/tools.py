"""Hermes tool handlers for CktClaw chip-design capabilities."""

from __future__ import annotations

import json
import re
import subprocess
import sys
from pathlib import Path
from typing import Any

from . import tool_runtime

PLUGIN_ROOT = Path(__file__).resolve().parent
SCRIPTS_DIR = PLUGIN_ROOT / "scripts"


def _json(data: dict[str, Any]) -> str:
    return json.dumps(data, indent=2, sort_keys=True)


def _script_json(script_name: str, argv: list[str], timeout_s: int) -> str:
    cmd = [sys.executable, str(SCRIPTS_DIR / script_name), *argv]
    try:
        proc = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout_s, check=False)
        if proc.stdout.strip():
            try:
                data = json.loads(proc.stdout)
            except json.JSONDecodeError:
                data = {"ok": proc.returncode == 0, "stdout": proc.stdout, "stderr": proc.stderr}
        else:
            data = {"ok": proc.returncode == 0, "stdout": "", "stderr": proc.stderr}
        data.setdefault("returncode", proc.returncode)
        data.setdefault("command", cmd)
        return _json(data)
    except subprocess.TimeoutExpired as exc:
        return _json({"ok": False, "error": f"{script_name} timed out after {exc.timeout}s", "command": cmd})
    except Exception as exc:
        return _json({"ok": False, "error": str(exc), "command": cmd})


def cktclaw_chip_install_toolchain(args: dict, **kwargs) -> str:
    del kwargs
    argv = ["--json"]
    if args.get("root"):
        argv.extend(["--root", str(args["root"])])
    if args.get("mode"):
        argv.extend(["--mode", str(args["mode"])])
    if args.get("dry_run"):
        argv.append("--dry-run")
    if args.get("include_hermes"):
        argv.append("--include-hermes")
    if args.get("skip_opensta_build"):
        argv.append("--skip-opensta-build")
    timeout = int(args.get("timeout_s") or (90 if args.get("dry_run") else 7200))
    return _script_json("install_toolchain.py", argv, timeout)


def cktclaw_chip_doctor(args: dict, **kwargs) -> str:
    del kwargs
    report = tool_runtime.doctor(args.get("root"))
    if args.get("format") == "markdown":
        lines = [
            "# CktClaw Chip Doctor",
            "",
            f"Root: `{report['root']}`",
            "",
            "## Repositories",
        ]
        for repo in report["repositories"]:
            mark = "OK" if repo["ready"] else "MISSING"
            lines.append(f"- {mark}: {repo['name']} -> `{repo['path']}`")
        lines.append("")
        lines.append("## Tools")
        for tool in report["tools"]:
            mark = "OK" if tool["found"] else "MISSING"
            lines.append(f"- {mark}: {tool['name']} ({tool['category']})")
        report["markdown"] = "\n".join(lines)
    return _json(report)


def cktclaw_chip_generate_mcp_config(args: dict, **kwargs) -> str:
    del kwargs
    selected = args.get("tools")
    if selected is not None and not isinstance(selected, list):
        selected = [str(selected)]
    config = tool_runtime.mcp_config(selected, args.get("root"))
    output_path = args.get("output_path")
    if output_path:
        path = Path(output_path).expanduser()
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps({"mcp_servers": config["mcp_servers"]}, indent=2), encoding="utf-8")
        config["output_path"] = str(path)
    return _json({"ok": True, **config})


def cktclaw_chip_spec_template(args: dict, **kwargs) -> str:
    del kwargs
    domain = str(args.get("domain") or "digital")
    block = str(args.get("block_name") or "<block_name>")
    target = str(args.get("target") or "<process_or_part>")
    sections = {
        "identity": {
            "block_name": block,
            "domain": domain,
            "target": target,
            "owner": "<owner>",
        },
        "intent": {
            "problem": "<what this block must do>",
            "non_goals": ["<out of scope item>"],
            "assumptions": ["<clocking, reset, supply, PDK, board, or model assumption>"],
        },
        "interfaces": {
            "ports_or_pins": ["<name, direction, width/type, timing/electrical contract>"],
            "protocols": ["<AXI/APB/stream/SPICE pins/RF ports/etc>"],
        },
        "targets": {
            "functionality": ["<must-pass behavior>"],
            "ppa_or_analog": ["<area, timing, power, gain, noise, bandwidth, linearity, yield>"],
            "reliability": ["<corners, voltage, temperature, aging, ESD, EM/IR>"],
        },
        "verification": {
            "golden_checks": ["<simulation, formal, assertions, measurements, DRC/LVS>"],
            "coverage": ["<functional, code, property, corner, Monte Carlo>"],
            "signoff_gates": ["<gate name and pass criterion>"],
        },
        "artifacts": {
            "inputs": ["<spec, RTL, netlist, schematic, constraints, PDK files>"],
            "outputs": ["<RTL, TB, reports, GDS, waveforms, measurements>"],
        },
    }
    if args.get("format") == "json":
        return _json({"ok": True, "template": sections})

    md = [
        f"# {block} Chip/IP Spec",
        "",
        f"- Domain: {domain}",
        f"- Target: {target}",
        "- Owner: <owner>",
        "",
        "## Intent",
        "- Problem: <what this block must do>",
        "- Non-goals: <out of scope item>",
        "- Assumptions: <clocking, reset, supply, PDK, board, or model assumption>",
        "",
        "## Interfaces",
        "- Ports or pins: <name, direction, width/type, timing/electrical contract>",
        "- Protocols: <AXI/APB/stream/SPICE pins/RF ports/etc>",
        "",
        "## Targets",
        "- Functionality: <must-pass behavior>",
        "- PPA or analog metrics: <area, timing, power, gain, noise, bandwidth, linearity, yield>",
        "- Reliability: <corners, voltage, temperature, aging, ESD, EM/IR>",
        "",
        "## Verification",
        "- Golden checks: <simulation, formal, assertions, measurements, DRC/LVS>",
        "- Coverage: <functional, code, property, corner, Monte Carlo>",
        "- Signoff gates: <gate name and pass criterion>",
        "",
        "## Artifacts",
        "- Inputs: <spec, RTL, netlist, schematic, constraints, PDK files>",
        "- Outputs: <RTL, TB, reports, GDS, waveforms, measurements>",
    ]
    return _json({"ok": True, "template": "\n".join(md)})


def _infer_domain(task: str, requested: str) -> str:
    if requested and requested != "auto":
        return requested
    text = task.lower()
    if any(word in text for word in ["spice", "opamp", "pll", "adc", "dac", "rf", "lna", "layout", "lvs", "drc"]):
        return "analog"
    if any(word in text for word in ["vivado", "fpga", "xdc", "bitstream"]):
        return "fpga"
    if any(word in text for word in ["hls", "c++", "kernel", "pragma"]):
        return "hls"
    if any(word in text for word in ["soc", "interconnect", "axi", "firmware"]):
        return "soc"
    return "digital"


def cktclaw_chip_flow_plan(args: dict, **kwargs) -> str:
    del kwargs
    task = str(args.get("task") or "")
    domain = _infer_domain(task, str(args.get("domain") or "auto"))
    constraints = str(args.get("constraints") or "")
    common = {
        "digital": {
            "skills": ["digital-chip-design", "digital-rtl-design", "digital-functional-verification", "digital-logic-synthesis", "digital-sta"],
            "tools": ["yosys", "iverilog", "vvp", "verilator", "sby", "opensta"],
            "stages": ["spec", "architecture", "rtl", "testbench", "simulation", "synthesis", "timing", "signoff"],
        },
        "analog": {
            "skills": ["analog-chip-design", "analog-circuit-design", "analog-circuit-simulation", "analog-layout", "analog-physical-verification"],
            "tools": ["ngspice", "xyce", "magic", "klayout", "netgen", "openvaf"],
            "stages": ["spec", "topology", "sizing", "simulation", "layout", "extraction", "lvs_drc", "post_layout_signoff"],
        },
        "fpga": {
            "skills": ["digital-fpga-emulation", "fpga-vivado-synth", "fpga-vivado-impl", "fpga-vivado-analysis", "fpga-vitis-hls-synthesis"],
            "tools": ["yosys", "verilator"],
            "stages": ["spec", "rtl_or_hls", "constraints", "synthesis", "implementation", "timing", "bitstream_handoff"],
        },
        "hls": {
            "skills": ["digital-hls", "rtl-enhancement-hls-generator", "fpga-vitis-hls-synthesis"],
            "tools": ["bambu", "verilator", "yosys"],
            "stages": ["algorithm_spec", "interface_contract", "hls_directives", "csim", "synthesis", "rtl_cosim", "handoff"],
        },
        "soc": {
            "skills": ["digital-soc-integration", "digital-architecture", "digital-compiler-toolchain", "digital-embedded-firmware"],
            "tools": ["yosys", "verilator", "gem5", "opensta"],
            "stages": ["spec", "ip_inventory", "bus_map", "integration", "firmware_boot", "verification", "ppa_review"],
        },
    }
    selected = common.get(domain, common["digital"])
    closure_keywords = [
        "rtl compile",
        "compile",
        "simulation",
        "simulate",
        "sim pass",
        "testbench",
        "yosys",
        "synthesis",
        "synthesize",
        "netlist",
        "qor",
        "pass",
        "编译",
        "仿真",
        "综合",
        "网表",
        "报告",
    ]
    needs_closure = domain == "digital" and any(keyword in task.lower() for keyword in closure_keywords)
    skills = list(selected["skills"])
    tools = list(selected["tools"])
    stages = list(selected["stages"])
    if needs_closure:
        skills = ["digital-eda-closure", *[skill for skill in skills if skill != "digital-eda-closure"]]
        tools = [*tools, "cktclaw_chip_closure_check"]
        stages = [
            "spec_contract",
            "rtl",
            "self_checking_testbench",
            "compile",
            "simulate",
            "synthesize",
            "qor",
            "closure_check",
            "evidence_summary",
        ]
    gates = [
        "Inputs are named and versioned",
        "Each generated artifact has a reproducer command",
        "Simulation or measurement evidence is captured",
        "Known limitations and next actions are explicit",
    ]
    if needs_closure:
        gates = [
            "Compile command exits 0 and compile log is saved",
            "Simulation command exits 0 and log contains the declared PASS token",
            "Yosys command exits 0 and writes both synthesized netlist and QoR report",
            "cktclaw_chip_closure_check reports all required gates as PASS before final answer",
            "Do not change the requested behavior, expected class, or stimulus only to make a failing test pass",
        ]
    return _json(
        {
            "ok": True,
            "task": task,
            "domain": domain,
            "constraints": constraints,
            "recommended_skills": skills,
            "recommended_tools": tools,
            "stages": stages,
            "acceptance_gates": gates,
        }
    )


def _read_text(path: Path, limit: int = 300_000) -> str:
    try:
        text = path.read_text(encoding="utf-8", errors="replace")
    except FileNotFoundError:
        return ""
    if len(text) > limit:
        return text[-limit:]
    return text


def _find_existing(paths: list[Path]) -> Path | None:
    for path in paths:
        if path.exists():
            return path
    return None


def _status(name: str, ok: bool, evidence: str, path: Path | None = None) -> dict[str, Any]:
    return {
        "name": name,
        "ok": ok,
        "status": "PASS" if ok else "FAIL",
        "evidence": evidence,
        "path": str(path) if path else "",
    }


def cktclaw_chip_closure_check(args: dict, **kwargs) -> str:
    del kwargs
    project_dir = Path(str(args.get("project_dir") or ".")).expanduser().resolve()
    outputs_dir = Path(str(args.get("outputs_dir") or project_dir / "outputs")).expanduser().resolve()
    pass_regex = str(args.get("expected_pass_regex") or r"(TEST\s+PASS|PASS)")

    compile_log = _find_existing([outputs_dir / "compile.log", outputs_dir / "iverilog.log"])
    sim_log = _find_existing([outputs_dir / "sim.log", outputs_dir / "vvp.log", outputs_dir / "simulation.log"])
    yosys_log = _find_existing([outputs_dir / "yosys.log", outputs_dir / "synth.log"])
    qor_report = Path(args["qor_report"]).expanduser().resolve() if args.get("qor_report") else _find_existing(
        [outputs_dir / "tiny_npu_qor.rpt", outputs_dir / "qor.rpt", outputs_dir / "synth.rpt"]
    )
    netlist = Path(args["netlist"]).expanduser().resolve() if args.get("netlist") else _find_existing(
        [outputs_dir / "tiny_npu_synth.v", outputs_dir / "synth.v", outputs_dir / "netlist.v"]
    )

    compile_text = _read_text(compile_log) if compile_log else ""
    sim_text = _read_text(sim_log) if sim_log else ""
    yosys_text = _read_text(yosys_log) if yosys_log else ""
    qor_text = _read_text(qor_report) if qor_report else ""

    compile_ok = bool(compile_log and not re.search(r"(error:|syntax error|\bfailed\b)", compile_text, re.I))
    sim_ok = bool(sim_log and re.search(pass_regex, sim_text, re.I) and not re.search(r"\b(TEST FAIL|fatal|assertion failed)\b", sim_text, re.I))
    yosys_ok = bool(yosys_log and not re.search(r"(ERROR:|syntax error|\bfailed\b)", yosys_text, re.I))
    netlist_ok = bool(netlist and netlist.exists() and netlist.stat().st_size > 0)
    qor_ok = bool(qor_report and qor_report.exists() and qor_report.stat().st_size > 0 and re.search(r"\bcells\b|\bwires\b|\bNumber of cells\b", qor_text, re.I))

    checks = [
        _status("compile", compile_ok, "compile log has no fatal diagnostics" if compile_ok else "compile log missing or contains an error", compile_log),
        _status("simulation", sim_ok, "simulation log contains requested PASS token" if sim_ok else "simulation PASS token missing or failure token present", sim_log),
        _status("yosys", yosys_ok, "Yosys log has no fatal diagnostics" if yosys_ok else "Yosys log missing or contains an error", yosys_log),
        _status("netlist", netlist_ok, "synthesized netlist exists" if netlist_ok else "synthesized netlist missing or empty", netlist),
        _status("qor", qor_ok, "QoR report exists and contains statistics" if qor_ok else "QoR report missing, empty, or lacks statistics", qor_report),
    ]

    hints: list[str] = []
    combined = "\n".join([compile_text, sim_text, yosys_text])
    if re.search(r"TEST FAIL|predicted|argmax|expected", sim_text, re.I):
        hints.append("For classification failures, inspect byte packing, read latency, row/column mapping, scoreboard logic, and signedness before changing labels or input vectors.")
    if re.search(r"Unsupported technology", yosys_text, re.I):
        hints.append("For this Yosys build, use 'stat -width' or a real liberty file instead of unsupported generic technology names.")
    if re.search(r"syntax error|Unable to bind|Unknown module", combined, re.I):
        hints.append("Fix syntax/module binding first, then rerun simulation before synthesis.")
    if re.search(r"rd_data|read", sim_text, re.I):
        hints.append("For synchronous register reads, sample read data after the clock edge updates rd_data.")
    if not hints and not all(check["ok"] for check in checks):
        hints.append("Rerun the earliest failing gate and make the smallest source change that addresses the logged root cause.")

    return _json(
        {
            "ok": all(check["ok"] for check in checks),
            "project_dir": str(project_dir),
            "outputs_dir": str(outputs_dir),
            "checks": checks,
            "debug_hints": hints,
            "required_before_final": "All checks must be PASS and artifacts must be cited with commands.",
        }
    )


def _make_eda_handler(tool_name: str):
    def _handler(args: dict, **kwargs) -> str:
        del kwargs
        return _json(tool_runtime.run_tool(tool_name, args))

    _handler.__name__ = f"cktclaw_chip_run_{tool_name}"
    return _handler


HANDLERS = {
    "cktclaw_chip_install_toolchain": cktclaw_chip_install_toolchain,
    "cktclaw_chip_doctor": cktclaw_chip_doctor,
    "cktclaw_chip_generate_mcp_config": cktclaw_chip_generate_mcp_config,
    "cktclaw_chip_spec_template": cktclaw_chip_spec_template,
    "cktclaw_chip_flow_plan": cktclaw_chip_flow_plan,
    "cktclaw_chip_closure_check": cktclaw_chip_closure_check,
}

for _tool_name in tool_runtime.TOOL_SPECS:
    HANDLERS[f"cktclaw_chip_run_{_tool_name}"] = _make_eda_handler(_tool_name)
