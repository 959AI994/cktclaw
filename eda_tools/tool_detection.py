"""
EDA Tool Detection — detect available open-source and proprietary EDA tools.

Scans the host for executables via ``shutil.which`` and captures version strings.
Generates a ``tool-manifest.json`` consumed by the MCP configurator and
the orchestrator engine to decide which execution path to use.
"""

import json
import os
import shutil
import subprocess
from dataclasses import dataclass, field, asdict
from datetime import datetime
from pathlib import Path
from typing import Literal

_WRAPPERS_DIR = Path(__file__).parent / "wrappers"

# ── Tool registry ────────────────────────────────────────────────────
# (name, commands_to_try, version_flag, category)
#  - commands_to_try: first match wins
#  - version_flag: argument that prints version (may be empty for tools
#    that print version on bare invocation or lack a flag)

_OPEN_SOURCE_TOOLS: list[tuple[str, list[str], str]] = [
    ("verilator",       ["verilator"],          "--version"),
    ("slang",           ["slang"],              "--version"),
    ("surelog",         ["surelog"],             "--version"),
    ("sv2v",            ["sv2v"],               "--version"),
    ("iverilog",        ["iverilog"],            "-V"),
    ("yosys",           ["yosys"],              "--version"),
    ("abc",             ["abc", os.environ.get("ABC_PATH", "")], "-h"),
    ("openroad",        ["openroad"],           "-version"),
    ("openlane",        ["openlane"],           "--version"),
    ("klayout",         ["klayout"],            "-v"),
    ("opensta",         ["sta", os.environ.get("OPENSTA_PATH", "")], "-version"),
    ("symbiyosys",      ["sby"],                "--help"),
    ("gem5",            ["gem5.opt", "gem5"],   "--version"),
    ("bambu-hls",       ["bambu"],              "--version"),
    ("nextpnr",         ["nextpnr-ice40", "nextpnr-ecp5", "nextpnr-gowin"], "--version"),
    ("openFPGALoader",  ["openFPGALoader"],     "--version"),
    ("cocotb",          ["cocotb-config"],       "--version"),
    ("llvm",            ["llvm-config"],         "--version"),
    ("gcc",             ["gcc"],                "--version"),
    ("openocd",         ["openocd"],            "--version"),
]

_PROPRIETARY_TOOLS: list[tuple[str, list[str]]] = [
    ("vcs",             ["vcs"]),
    ("xcelium",         ["xrun", "xmsim"]),
    ("design-compiler", ["dc_shell", "dc_shell-t"]),
    ("innovus",         ["innovus"]),
    ("questasim",       ["vsim", "questa", "questasim"]),
    ("primetime",       ["pt_shell", "pt_shell64"]),
    ("formality",       ["formality", "fm_shell"]),
]

_WRAPPER_NAMES = [
    "wrap-yosys.sh",
    "wrap-opensta.sh",
    "wrap-openroad.sh",
    "wrap-verilator-sim.sh",
    "wrap-klayout.sh",
    "wrap-bambu.sh",
    "wrap-gem5.sh",
    "wrap-symbiflow.sh",
]


# ── Data structures ──────────────────────────────────────────────────

@dataclass
class ToolStatus:
    name: str
    command: str
    status: Literal["FOUND", "MISSING", "PROPRIETARY_ONLY"]
    version: str = ""
    path: str = ""
    category: str = "open_source"


@dataclass
class ToolManifest:
    tools: list[ToolStatus] = field(default_factory=list)
    wrappers: dict[str, bool] = field(default_factory=dict)
    detected_at: str = ""

    def found_tools(self) -> list[ToolStatus]:
        return [t for t in self.tools if t.status == "FOUND"]

    def missing_tools(self) -> list[ToolStatus]:
        return [t for t in self.tools if t.status == "MISSING"]

    def is_tool_available(self, name: str) -> bool:
        return any(t.name == name and t.status == "FOUND" for t in self.tools)


# ── Detection logic ──────────────────────────────────────────────────

def _try_version(cmd: str, flag: str) -> str:
    """Run *cmd flag* and return first non-empty line, or ''."""
    if not flag:
        return ""
    try:
        proc = subprocess.run(
            [cmd, flag],
            capture_output=True, text=True, timeout=10,
        )
        output = (proc.stdout or proc.stderr or "").strip()
        for line in output.splitlines():
            stripped = line.strip()
            if stripped:
                return stripped[:200]
        return ""
    except Exception:
        return ""


def detect_tool(
    name: str,
    commands: list[str],
    version_flag: str = "",
    category: str = "open_source",
) -> ToolStatus:
    """Detect a single tool by trying each command candidate."""
    for cmd in commands:
        if not cmd:
            continue
        path = shutil.which(cmd)
        if path:
            version = _try_version(path, version_flag)
            status = "PROPRIETARY_ONLY" if category == "proprietary" else "FOUND"
            return ToolStatus(
                name=name, command=cmd, status=status,
                version=version, path=path, category=category,
            )
    status_val: Literal["FOUND", "MISSING", "PROPRIETARY_ONLY"] = "MISSING"
    return ToolStatus(
        name=name, command=commands[0] if commands else name,
        status=status_val, category=category,
    )


def detect_wrappers() -> dict[str, bool]:
    """Check existence and executable permission for each wrapper script."""
    result: dict[str, bool] = {}
    for w in _WRAPPER_NAMES:
        p = _WRAPPERS_DIR / w
        result[w] = p.is_file() and os.access(p, os.X_OK)
    return result


def detect_all_tools() -> ToolManifest:
    """Scan the host for all registered EDA tools and wrappers."""
    tools: list[ToolStatus] = []

    for name, cmds, vflag in _OPEN_SOURCE_TOOLS:
        tools.append(detect_tool(name, cmds, vflag, "open_source"))

    for name, cmds in _PROPRIETARY_TOOLS:
        found = detect_tool(name, cmds, "", "proprietary")
        if found.path:
            found.status = "PROPRIETARY_ONLY"
        tools.append(found)

    return ToolManifest(
        tools=tools,
        wrappers=detect_wrappers(),
        detected_at=datetime.now().isoformat(),
    )


# ── Persistence ──────────────────────────────────────────────────────

def write_tool_manifest(manifest: ToolManifest, path: str | Path) -> None:
    """Serialise manifest to JSON."""
    data = {
        "detected_at": manifest.detected_at,
        "tools": [asdict(t) for t in manifest.tools],
        "wrappers": manifest.wrappers,
    }
    Path(path).write_text(json.dumps(data, indent=2, ensure_ascii=False))


def load_tool_manifest(path: str | Path) -> ToolManifest:
    """Deserialise manifest from JSON."""
    raw = json.loads(Path(path).read_text())
    tools = [ToolStatus(**t) for t in raw.get("tools", [])]
    return ToolManifest(
        tools=tools,
        wrappers=raw.get("wrappers", {}),
        detected_at=raw.get("detected_at", ""),
    )
