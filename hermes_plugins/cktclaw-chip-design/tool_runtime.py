"""Shared chip-design tool metadata, detection, and subprocess wrappers."""

from __future__ import annotations

import json
import os
import re
import shlex
import shutil
import subprocess
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

PLUGIN_ROOT = Path(__file__).resolve().parent
DEFAULT_ROOT = Path(os.environ.get("CKTCLAW_CHIP_ROOT", "~/.cktclaw-chip")).expanduser()

REPO_SPECS: dict[str, dict[str, str]] = {
    "digital-chip-design-agents": {
        "url": "https://github.com/chuanseng-ng/digital-chip-design-agents.git",
        "path": "repos/digital-chip-design-agents",
        "required": "plugins",
    },
    "analog-chip-design-agents": {
        "url": "https://github.com/chuanseng-ng/analog-chip-design-agents.git",
        "path": "repos/analog-chip-design-agents",
        "required": "plugins",
    },
    "verilog-generator": {
        "url": "https://github.com/Eriemon/verilog-generator.git",
        "path": "repos/verilog-generator",
        "required": "SKILL.md",
    },
    "hls-generator": {
        "url": "https://github.com/Eriemon/hls-generator.git",
        "path": "repos/hls-generator",
        "required": "SKILL.md",
    },
    "RTLFixer": {
        "url": "https://github.com/NVlabs/RTLFixer.git",
        "path": "repos/RTLFixer",
        "required": "src",
    },
    "FPGA-Agent-skills": {
        "url": "https://github.com/adeleempurpled290/FPGA-Agent-skills.git",
        "path": "repos/FPGA-Agent-skills",
        "required": "vivado-tcl/SKILL.md",
    },
    "AI4EDA-OpenABC-Data-Toolkit": {
        "url": "https://github.com/959AI994/AI4EDA-OpenABC-Data-Toolkit.git",
        "path": "repos/AI4EDA-OpenABC-Data-Toolkit",
        "required": "ai4eda-toolkit",
    },
    "hermes-agent": {
        "url": "https://github.com/NousResearch/hermes-agent.git",
        "path": "repos/hermes-agent",
        "required": "pyproject.toml",
    },
}

TOOL_SPECS: dict[str, dict[str, Any]] = {
    "yosys": {
        "commands": ["yosys"],
        "description": "Run Yosys synthesis and return cells, area, error, and warning summaries.",
        "category": "digital",
        "timeout_s": 300,
    },
    "iverilog": {
        "commands": ["iverilog"],
        "description": "Compile Verilog/SystemVerilog simulation sources with Icarus Verilog.",
        "category": "digital",
        "timeout_s": 180,
    },
    "vvp": {
        "commands": ["vvp"],
        "description": "Run an Icarus Verilog simulation output with vvp.",
        "category": "digital",
        "timeout_s": 180,
    },
    "verilator": {
        "commands": ["verilator"],
        "description": "Run Verilator lint or simulation-oriented commands and summarize diagnostics.",
        "category": "digital",
        "timeout_s": 300,
    },
    "sby": {
        "commands": ["sby"],
        "description": "Run SymbiYosys bounded formal checks and summarize proof status.",
        "category": "digital",
        "timeout_s": 3600,
    },
    "opensta": {
        "commands": ["sta", "opensta"],
        "description": "Run OpenSTA timing analysis from Tcl or command arguments.",
        "category": "digital",
        "timeout_s": 300,
    },
    "openroad": {
        "commands": ["openroad"],
        "description": "Run OpenROAD physical design stages and summarize timing/DRC signals.",
        "category": "digital",
        "timeout_s": 600,
    },
    "bambu": {
        "commands": ["bambu"],
        "description": "Run Bambu HLS synthesis for C/C++ kernels.",
        "category": "digital",
        "timeout_s": 600,
    },
    "gem5": {
        "commands": ["gem5.opt", "gem5"],
        "description": "Run a short gem5 architectural simulation and summarize stats when present.",
        "category": "digital",
        "timeout_s": 600,
    },
    "ngspice": {
        "commands": ["ngspice"],
        "description": "Run ngspice batch DC, AC, transient, noise, or measure analysis.",
        "category": "analog",
        "timeout_s": 300,
    },
    "xyce": {
        "commands": ["Xyce", "xyce"],
        "description": "Run Xyce SPICE-compatible simulation for analog or mixed-signal circuits.",
        "category": "analog",
        "timeout_s": 600,
    },
    "magic": {
        "commands": ["magic"],
        "description": "Run Magic layout DRC, extraction, or Tcl automation.",
        "category": "analog",
        "timeout_s": 300,
    },
    "klayout": {
        "commands": ["klayout"],
        "description": "Run KLayout batch layout checks, DRC scripts, or GDS inspection.",
        "category": "analog",
        "timeout_s": 300,
    },
    "netgen": {
        "commands": ["netgen"],
        "description": "Run Netgen LVS or netlist comparison tasks.",
        "category": "analog",
        "timeout_s": 300,
    },
    "openvaf": {
        "commands": ["openvaf"],
        "description": "Compile Verilog-A compact models to OSDI with OpenVAF.",
        "category": "analog",
        "timeout_s": 300,
    },
    "openems": {
        "commands": ["openEMS", "openems"],
        "description": "Run openEMS electromagnetic simulations for RF/package structures.",
        "category": "analog",
        "timeout_s": 900,
    },
    "openlane2": {
        "commands": ["openlane2", "openlane"],
        "description": "Run OpenLane2 RTL-to-GDS flows when installed.",
        "category": "digital",
        "timeout_s": 1800,
    },
    "ai4eda": {
        "commands": ["ai4eda-toolkit"],
        "description": "Run AI4EDA OpenABC data toolkit commands for circuit datasets and metrics.",
        "category": "aux",
        "timeout_s": 600,
    },
}

PROPRIETARY_DETECT_ONLY: dict[str, list[str]] = {
    "vcs": ["vcs"],
    "xcelium": ["xrun", "xmsim"],
    "design-compiler": ["dc_shell", "dc_shell-t"],
    "innovus": ["innovus"],
    "questasim": ["vsim", "questa", "questasim"],
    "primetime": ["pt_shell", "pt_shell64"],
    "formality": ["formality", "fm_shell"],
}


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def json_dumps(data: dict[str, Any]) -> str:
    return json.dumps(data, indent=2, sort_keys=True)


def chip_root(root: str | None = None) -> Path:
    if root:
        return Path(root).expanduser().resolve()
    return DEFAULT_ROOT.resolve()


def _which(candidates: list[str], env: dict[str, str] | None = None) -> str:
    path = (env or os.environ).get("PATH")
    for cmd in candidates:
        found = shutil.which(cmd, path=path)
        if found:
            return found
    return ""


def _build_env(args: dict[str, Any]) -> dict[str, str]:
    env = os.environ.copy()
    overrides = args.get("env") or {}
    if isinstance(overrides, dict):
        env.update({str(k): str(v) for k, v in overrides.items()})
    root = chip_root(args.get("root") or None)
    env.setdefault("CKTCLAW_CHIP_ROOT", str(root))
    env.setdefault("CHIP_AGENTS_ROOT", str(root / "repos" / "digital-chip-design-agents" / "plugins"))
    env.setdefault("ANALOG_CHIP_AGENTS_ROOT", str(root / "repos" / "analog-chip-design-agents" / "plugins"))
    env.setdefault("VERILOG_GENERATOR_ROOT", str(root / "repos" / "verilog-generator"))
    env.setdefault("HLS_GENERATOR_ROOT", str(root / "repos" / "hls-generator"))
    env.setdefault("RTLFIXER_ROOT", str(root / "repos" / "RTLFixer"))
    env.setdefault("FPGA_AGENT_SKILLS_ROOT", str(root / "repos" / "FPGA-Agent-skills"))
    env.setdefault("CKTCLAW_AI4EDA_PATH", str(root / "repos" / "AI4EDA-OpenABC-Data-Toolkit"))
    ai4eda_bin = root / "repos" / "AI4EDA-OpenABC-Data-Toolkit" / "ai4eda-toolkit"
    if ai4eda_bin.exists():
        env["AI4EDA_BIN"] = str(ai4eda_bin)
        env["PATH"] = f"{ai4eda_bin.parent}:{env.get('PATH', '')}"
    oss_bin = root / "eda" / "oss-cad-suite" / "bin"
    opensta_bin = root / "eda" / "opensta-install" / "bin"
    env["PATH"] = f"{oss_bin}:{opensta_bin}:{env.get('PATH', '')}"
    return env


def _write_temp(suffix: str, content: str) -> str:
    handle = tempfile.NamedTemporaryFile(mode="w", suffix=suffix, delete=False, encoding="utf-8")
    with handle:
        handle.write(content)
        if not content.endswith("\n"):
            handle.write("\n")
    return handle.name


def _build_command(tool_name: str, executable: str, args: dict[str, Any]) -> tuple[list[str], list[str]]:
    cleanup: list[str] = []
    raw_args = args.get("args")
    if raw_args is None:
        raw_args = []
    if not isinstance(raw_args, list):
        raw_args = [str(raw_args)]
    raw_args = [str(item) for item in raw_args]

    if args.get("command") and not raw_args and not args.get("script") and not args.get("tcl_script") and not args.get("netlist_file"):
        parts = shlex.split(str(args["command"]))
        if parts and Path(parts[0]).name.lower() in {Path(executable).name.lower(), tool_name.lower()}:
            parts = parts[1:]
        return [executable, *parts], cleanup

    if tool_name == "yosys":
        if args.get("script"):
            return [executable, "-p", str(args["script"]), *raw_args], cleanup
        if args.get("script_file"):
            return [executable, str(args["script_file"]), *raw_args], cleanup

    if tool_name in {"openroad", "opensta"} and args.get("tcl_script"):
        script_path = _write_temp(".tcl", str(args["tcl_script"]))
        cleanup.append(script_path)
        return [executable, script_path, *raw_args], cleanup

    if tool_name == "magic" and args.get("tcl_script"):
        script_path = _write_temp(".tcl", str(args["tcl_script"]) + "\nquit -noprompt\n")
        cleanup.append(script_path)
        return [executable, "-dnull", "-noconsole", script_path, *raw_args], cleanup

    if tool_name in {"ngspice", "xyce"}:
        if args.get("netlist_file"):
            if tool_name == "ngspice":
                return [executable, "-b", str(args["netlist_file"]), *raw_args], cleanup
            return [executable, str(args["netlist_file"]), *raw_args], cleanup
        if args.get("script"):
            script_path = _write_temp(".cir", str(args["script"]))
            cleanup.append(script_path)
            if tool_name == "ngspice":
                return [executable, "-b", script_path, *raw_args], cleanup
            return [executable, script_path, *raw_args], cleanup

    return [executable, *raw_args], cleanup


def _summary_for_tool(tool_name: str, text: str, returncode: int) -> dict[str, Any]:
    errors = [line.strip() for line in text.splitlines() if re.search(r"\b(error|fatal|failed|abort)\b", line, re.I)]
    warnings = [line.strip() for line in text.splitlines() if re.search(r"\b(warning|warn)\b", line, re.I)]
    summary: dict[str, Any] = {
        "error_count": len(errors),
        "warning_count": len(warnings),
    }

    if tool_name == "yosys":
        cells = re.search(r"Number of cells:\s+(\d+)", text)
        area = re.search(r"Chip area for (?:top )?module[^:]*:\s+([-\d.]+)", text)
        if cells:
            summary["cells"] = int(cells.group(1))
        if area:
            summary["chip_area_um2"] = float(area.group(1))
    elif tool_name in {"opensta", "openroad"}:
        for key, pattern in {
            "wns_ns": r"\bwns\b\s+([-\d.]+)",
            "tns_ns": r"\btns\b\s+([-\d.]+)",
            "drc_violations": r"(\d+)\s+(?:DRC\s+)?violations?",
        }.items():
            match = re.search(pattern, text, re.I)
            if match:
                value = match.group(1)
                summary[key] = float(value) if "." in value or "-" in value else int(value)
    elif tool_name in {"ngspice", "xyce"}:
        measures = {}
        for match in re.finditer(r"^\s*([A-Za-z_]\w*)\s*=\s*([-+]?[\d.eE]+)", text, re.M):
            measures[match.group(1)] = float(match.group(2))
        summary["measures"] = measures
        summary["convergence"] = not bool(re.search(r"(no convergence|singular matrix|iteration limit)", text, re.I))
    elif tool_name == "sby":
        summary["proved"] = len(re.findall(r"\bPASS\b|\bproved\b", text, re.I))
        summary["failed"] = len(re.findall(r"\bFAIL\b|\bfailed\b", text, re.I))
    elif tool_name == "gem5":
        sim_insts = re.search(r"simInsts\s+(\d+)", text)
        host_seconds = re.search(r"hostSeconds\s+([-\d.]+)", text)
        if sim_insts:
            summary["sim_insts"] = int(sim_insts.group(1))
        if host_seconds:
            summary["host_seconds"] = float(host_seconds.group(1))

    if returncode != 0 or errors:
        summary["status"] = "FAIL"
    elif warnings:
        summary["status"] = "WARN"
    else:
        summary["status"] = "PASS"
    return summary


def run_tool(tool_name: str, args: dict[str, Any] | None = None) -> dict[str, Any]:
    args = args or {}
    spec = TOOL_SPECS.get(tool_name)
    if not spec:
        return {"ok": False, "tool": tool_name, "error": f"Unsupported chip EDA tool: {tool_name}"}

    env = _build_env(args)
    executable = _which(spec["commands"], env)
    if not executable:
        return {
            "ok": False,
            "tool": tool_name,
            "status": "MISSING",
            "error": f"{tool_name} not found",
            "tried": spec["commands"],
            "hint": "Run cktclaw_chip_install_toolchain or add the tool to PATH.",
        }

    cleanup: list[str] = []
    try:
        cmd, cleanup = _build_command(tool_name, executable, args)
        timeout = int(args.get("timeout_s") or spec.get("timeout_s") or 300)
        working_dir = Path(args.get("working_dir") or os.getcwd()).expanduser()
        proc = subprocess.run(
            cmd,
            cwd=str(working_dir),
            env=env,
            capture_output=True,
            text=True,
            timeout=timeout,
            check=False,
        )
        combined = (proc.stdout or "") + ("\n" + proc.stderr if proc.stderr else "")
        summary = _summary_for_tool(tool_name, combined, proc.returncode)
        return {
            "ok": proc.returncode == 0,
            "tool": tool_name,
            "command": cmd,
            "working_dir": str(working_dir),
            "returncode": proc.returncode,
            "summary": summary,
            "stdout": proc.stdout[-20000:],
            "stderr": proc.stderr[-12000:],
        }
    except subprocess.TimeoutExpired as exc:
        return {"ok": False, "tool": tool_name, "status": "TIMEOUT", "error": f"Timed out after {exc.timeout}s"}
    except Exception as exc:  # Defensive plugin boundary: never raise into Hermes.
        return {"ok": False, "tool": tool_name, "status": "ERROR", "error": str(exc)}
    finally:
        for path in cleanup:
            try:
                Path(path).unlink()
            except OSError:
                pass


def detect_repositories(root: Path) -> list[dict[str, Any]]:
    result = []
    for name, spec in REPO_SPECS.items():
        path = root / spec["path"]
        required = path / spec["required"]
        result.append(
            {
                "name": name,
                "url": spec["url"],
                "path": str(path),
                "present": path.exists(),
                "ready": required.exists(),
                "required": spec["required"],
            }
        )
    return result


def detect_tools(root: str | None = None) -> list[dict[str, Any]]:
    env = _build_env({"root": str(chip_root(root)) if root else None})
    tools = []
    for name, spec in TOOL_SPECS.items():
        found = _which(spec["commands"], env)
        tools.append(
            {
                "name": name,
                "category": spec["category"],
                "commands": spec["commands"],
                "found": bool(found),
                "path": found,
                "installable_by_plugin": name in {"yosys", "iverilog", "vvp", "verilator", "sby"},
            }
        )
    for name, commands in PROPRIETARY_DETECT_ONLY.items():
        found = _which(commands, env)
        tools.append(
            {
                "name": name,
                "category": "proprietary-detect-only",
                "commands": commands,
                "found": bool(found),
                "path": found,
                "installable_by_plugin": False,
            }
        )
    return tools


def doctor(root: str | None = None) -> dict[str, Any]:
    root_path = chip_root(root)
    return {
        "ok": True,
        "checked_at": utc_now(),
        "root": str(root_path),
        "repositories": detect_repositories(root_path),
        "tools": detect_tools(str(root_path)),
        "plugin_root": str(PLUGIN_ROOT),
    }


def mcp_config(tool_names: list[str] | None = None, root: str | None = None) -> dict[str, Any]:
    selected = tool_names or list(TOOL_SPECS)
    server_script = PLUGIN_ROOT / "scripts" / "mcp_tool_server.py"
    root_path = chip_root(root)
    servers: dict[str, Any] = {}
    for name in selected:
        if name not in TOOL_SPECS:
            continue
        servers[f"cktclaw-{name}"] = {
            "command": "python3",
            "args": [str(server_script), "--tool", name],
            "env": {
                "CKTCLAW_CHIP_ROOT": str(root_path),
                "TOOL_TIMEOUT_S": str(TOOL_SPECS[name].get("timeout_s", 300)),
            },
        }
    return {
        "mcp_servers": servers,
        "generated_at": utc_now(),
        "plugin_root": str(PLUGIN_ROOT),
        "root": str(root_path),
    }
