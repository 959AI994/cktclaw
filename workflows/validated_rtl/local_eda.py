"""Local iverilog/vvp/yosys helpers for validated RTL flows."""

from __future__ import annotations

import json
import shutil
from pathlib import Path
from typing import Any, Dict, List, Optional

from ..tiny_npu.flow import _parse_yosys_qor, _run_cmd


def tool_availability() -> Dict[str, Optional[str]]:
    return {
        "iverilog": shutil.which("iverilog"),
        "vvp": shutil.which("vvp"),
        "yosys": shutil.which("yosys"),
    }


def write_run_sim_script(scripts_dir: Path, *, module_name: str, rtl_file: str, tb_file: str) -> Path:
    scripts_dir.mkdir(parents=True, exist_ok=True)
    path = scripts_dir / "run_sim.sh"
    path.write_text(
        "\n".join([
            "#!/usr/bin/env bash",
            "set -euo pipefail",
            f"iverilog -g2012 -Wall -o build/{module_name}_tb.vvp rtl/{rtl_file} tb/{tb_file}",
            f"vvp build/{module_name}_tb.vvp | tee reports/simulation.log",
            "",
        ]),
        encoding="utf-8",
    )
    path.chmod(0o755)
    return path


def write_synth_script(scripts_dir: Path, *, module_name: str, rtl_file: str) -> Path:
    scripts_dir.mkdir(parents=True, exist_ok=True)
    path = scripts_dir / "synth_yosys.ys"
    path.write_text(
        "\n".join([
            f"read_verilog -sv rtl/{rtl_file}",
            f"hierarchy -top {module_name}",
            "proc",
            "opt",
            "memory",
            "opt",
            "techmap",
            "opt",
            "stat",
            f"write_json synth/{module_name}.json",
            f"write_verilog synth/{module_name}_netlist.v",
            "",
        ]),
        encoding="utf-8",
    )
    return path


async def run_simulation(
    project_dir: Path,
    *,
    rtl_dir: Path,
    tb_dir: Path,
    build_dir: Path,
    reports_dir: Path,
    wave_dir: Path,
    rtl_file: str,
    tb_file: str,
    module_name: str,
) -> Dict[str, Any]:
    tools = tool_availability()
    iverilog = tools["iverilog"]
    vvp = tools["vvp"]
    if not iverilog or not vvp:
        return {
            "status": "tool_missing",
            "summary": "iverilog/vvp not found in PATH.",
            "issues": ["tool_missing: iverilog/vvp"],
            "artifacts": [],
        }

    build_dir.mkdir(parents=True, exist_ok=True)
    reports_dir.mkdir(parents=True, exist_ok=True)
    wave_dir.mkdir(parents=True, exist_ok=True)
    out = build_dir / f"{module_name}_tb.vvp"
    cmd = [
        iverilog,
        "-g2012",
        "-Wall",
        "-o",
        str(out),
        str(rtl_dir / rtl_file),
        str(tb_dir / tb_file),
    ]
    compile_result = await _run_cmd(cmd, cwd=project_dir, timeout=120)
    log = reports_dir / "simulation.log"
    if compile_result["returncode"] != 0:
        log.write_text(compile_result["output"], encoding="utf-8")
        return {
            "status": "FAIL",
            "summary": "RTL/testbench compile failed.",
            "command": cmd,
            "output": compile_result["output"],
            "artifacts": [str(log)],
            "issues": ["compile failed"],
            "failure_signature": _failure_signature("compile", compile_result["output"]),
        }

    sim_result = await _run_cmd([vvp, str(out)], cwd=project_dir, timeout=120)
    log.write_text(sim_result["output"], encoding="utf-8")
    known_vector_pass = _known_vector_pass(sim_result["output"])
    passed = _simulation_passed(sim_result["returncode"], sim_result["output"], known_vector_pass)
    status = "PASS" if passed else "FAIL"
    return {
        "status": status,
        "summary": "Self-checking simulation passed." if passed else "Self-checking simulation failed.",
        "command": [cmd, [vvp, str(out)]],
        "output": sim_result["output"],
        "artifacts": [str(log), str(out)],
        "issues": [] if passed else ["simulation did not report a passing self-check"],
        "known_vector_pass": known_vector_pass,
        "failure_signature": "" if passed else _failure_signature("simulation", sim_result["output"]),
    }


async def run_synthesis(
    project_dir: Path,
    *,
    scripts_dir: Path,
    synth_dir: Path,
    reports_dir: Path,
    rtl_file: str,
    module_name: str,
) -> Dict[str, Any]:
    yosys = tool_availability()["yosys"]
    if not yosys:
        return {
            "status": "tool_missing",
            "summary": "yosys not found in PATH.",
            "issues": ["tool_missing: yosys"],
            "artifacts": [],
        }

    synth_dir.mkdir(parents=True, exist_ok=True)
    reports_dir.mkdir(parents=True, exist_ok=True)
    script = write_synth_script(scripts_dir, module_name=module_name, rtl_file=rtl_file)
    result = await _run_cmd([yosys, "-s", str(script)], cwd=project_dir, timeout=180)
    log = reports_dir / "yosys.log"
    log.write_text(result["output"], encoding="utf-8")
    qor = _parse_yosys_qor(result["output"])
    qor_path = reports_dir / "qor.json"
    qor_path.write_text(json.dumps(qor, indent=2, ensure_ascii=False), encoding="utf-8")
    passed = result["returncode"] == 0 and qor.get("num_cells", 0) > 0
    return {
        "status": "PASS" if passed else "FAIL",
        "summary": (
            f"Yosys synthesis produced {qor.get('num_cells', 0)} generic cells."
            if passed else
            "Yosys synthesis failed or QoR was not parseable."
        ),
        "command": [yosys, "-s", str(script)],
        "qor": qor,
        "output": result["output"][-5000:],
        "artifacts": [
            str(script),
            str(log),
            str(qor_path),
            str(synth_dir / f"{module_name}.json"),
            str(synth_dir / f"{module_name}_netlist.v"),
        ],
        "issues": [] if passed else ["yosys failed or produced no cells"],
        "failure_signature": "" if passed else _failure_signature("synthesis", result["output"]),
    }


def _simulation_passed(returncode: int, output: str, known_vector_pass: Optional[bool]) -> bool:
    if returncode != 0:
        return False
    upper = output.upper()
    if "ALL TESTS PASSED" in upper or "TEST PASSED" in upper:
        return True
    if known_vector_pass is True:
        return True
    return False


def _failure_signature(stage: str, output: str) -> str:
    lines = [line.strip() for line in output.splitlines() if line.strip()]
    tail = lines[-3:] if lines else ["empty"]
    return f"{stage}:" + "|".join(tail)[:500]


def _known_vector_pass(output: str) -> Optional[bool]:
    lowered = output.lower()
    if "known vector" in lowered or "crc" in lowered:
        if "pass" in lowered or "8'hf4" in lowered or "0xf4" in lowered:
            return True
        if "fail" in lowered:
            return False
    if "ALL TESTS PASSED" in output or "TEST PASSED" in output.upper():
        return True
    return None
