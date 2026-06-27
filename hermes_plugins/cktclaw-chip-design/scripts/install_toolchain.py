#!/usr/bin/env python3
"""Install chip-design repos and optional open-source EDA tools."""

from __future__ import annotations

import argparse
import json
import os
import platform
import shutil
import subprocess
import sys
import tarfile
import urllib.request
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import tool_runtime  # noqa: E402

OSS_FALLBACK_RELEASE = "2024-12-23"
OSS_FALLBACK_DATE = "20241223"


class Installer:
    def __init__(self, root: Path, dry_run: bool):
        self.root = root
        self.dry_run = dry_run
        self.actions: list[dict] = []
        self.errors: list[str] = []

    def record(self, action: str, command: list[str] | None = None, cwd: Path | None = None, skipped: bool = False) -> None:
        self.actions.append(
            {
                "action": action,
                "command": command or [],
                "cwd": str(cwd) if cwd else "",
                "skipped": skipped,
            }
        )

    def run(self, command: list[str], cwd: Path | None = None) -> bool:
        self.record("run", command, cwd)
        if self.dry_run:
            return True
        proc = subprocess.run(command, cwd=str(cwd) if cwd else None, text=True, capture_output=True, check=False)
        if proc.returncode != 0:
            self.errors.append(f"{' '.join(command)} failed: {proc.stderr[-2000:]}")
            return False
        return True

    def ensure_dir(self, path: Path) -> None:
        self.record("mkdir", ["mkdir", "-p", str(path)], skipped=path.exists())
        if not self.dry_run:
            path.mkdir(parents=True, exist_ok=True)


def _clone_repo(installer: Installer, name: str, spec: dict) -> None:
    path = installer.root / spec["path"]
    if (path / spec["required"]).exists():
        installer.record(f"repo ready: {name}", skipped=True)
        return
    installer.ensure_dir(path.parent)
    if path.exists() and any(path.iterdir()):
        installer.record(f"repo present but incomplete: {name}", skipped=True)
        installer.errors.append(f"{name} exists but required path is missing: {path / spec['required']}")
        return
    installer.run(["git", "clone", "--depth", "1", spec["url"], str(path)])


def _platform_asset() -> str:
    system = platform.system().lower()
    machine = platform.machine().lower()
    if machine in {"amd64", "x86_64"}:
        machine = "x64"
    elif machine in {"aarch64", "arm64"}:
        machine = "arm64"
    if system == "darwin":
        return f"darwin-{machine}"
    return f"linux-{machine}"


def _latest_oss_url(asset_platform: str) -> str:
    api = "https://api.github.com/repos/YosysHQ/oss-cad-suite-build/releases/latest"
    try:
        with urllib.request.urlopen(api, timeout=20) as response:
            payload = json.loads(response.read().decode("utf-8"))
        for asset in payload.get("assets", []):
            url = asset.get("browser_download_url", "")
            if f"oss-cad-suite-{asset_platform}-" in url and url.endswith(".tgz"):
                return url
    except Exception:
        pass
    return (
        "https://github.com/YosysHQ/oss-cad-suite-build/releases/download/"
        f"{OSS_FALLBACK_RELEASE}/oss-cad-suite-{asset_platform}-{OSS_FALLBACK_DATE}.tgz"
    )


def _install_oss_cad_suite(installer: Installer) -> None:
    eda_root = installer.root / "eda"
    oss_dir = eda_root / "oss-cad-suite"
    yosys = oss_dir / "bin" / "yosys"
    if yosys.exists():
        installer.record("oss-cad-suite ready", skipped=True)
        return
    installer.ensure_dir(eda_root)
    asset_platform = _platform_asset()
    url = _latest_oss_url(asset_platform)
    tarball = eda_root / "oss-cad-suite.tgz"
    installer.record("download oss-cad-suite", ["download", url, str(tarball)])
    if installer.dry_run:
        return
    try:
        urllib.request.urlretrieve(url, tarball)
        with tarfile.open(tarball, "r:gz") as archive:
            archive.extractall(eda_root)
        tarball.unlink(missing_ok=True)
    except Exception as exc:
        installer.errors.append(f"oss-cad-suite install failed: {exc}")


def _build_opensta(installer: Installer, skip_build: bool) -> None:
    if shutil.which("sta") or (installer.root / "eda" / "opensta-install" / "bin" / "sta").exists():
        installer.record("OpenSTA ready", skipped=True)
        return
    if skip_build:
        installer.record("OpenSTA build skipped", skipped=True)
        return
    if not (shutil.which("cmake") and shutil.which("make") and shutil.which("git")):
        installer.errors.append("OpenSTA build needs git, cmake, and make")
        return
    src = installer.root / "eda" / "OpenSTA"
    build = src / "build"
    prefix = installer.root / "eda" / "opensta-install"
    if not src.exists():
        installer.run(["git", "clone", "--depth", "1", "https://github.com/The-OpenROAD-Project/OpenSTA.git", str(src)])
    installer.ensure_dir(build)
    installer.run(["cmake", "..", f"-DCMAKE_INSTALL_PREFIX={prefix}", "-DCMAKE_BUILD_TYPE=Release"], cwd=build)
    installer.run(["make", f"-j{os.cpu_count() or 2}"], cwd=build)
    installer.run(["make", "install"], cwd=build)


def _write_env(installer: Installer) -> None:
    env_path = installer.root / ".env"
    ai4eda = installer.root / "repos" / "AI4EDA-OpenABC-Data-Toolkit"
    text = f"""# Generated by cktclaw-chip-design install_toolchain.py
export CKTCLAW_CHIP_ROOT="{installer.root}"
export PATH="{installer.root}/eda/oss-cad-suite/bin:{installer.root}/eda/opensta-install/bin:{ai4eda}:$PATH"
export CHIP_AGENTS_ROOT="{installer.root}/repos/digital-chip-design-agents/plugins"
export ANALOG_CHIP_AGENTS_ROOT="{installer.root}/repos/analog-chip-design-agents/plugins"
export VERILOG_GENERATOR_ROOT="{installer.root}/repos/verilog-generator"
export HLS_GENERATOR_ROOT="{installer.root}/repos/hls-generator"
export RTLFIXER_ROOT="{installer.root}/repos/RTLFixer"
export FPGA_AGENT_SKILLS_ROOT="{installer.root}/repos/FPGA-Agent-skills"
export CKTCLAW_AI4EDA_PATH="{ai4eda}"
export AI4EDA_BIN="{ai4eda}/ai4eda-toolkit"
"""
    installer.record("write env", ["write", str(env_path)])
    if not installer.dry_run:
        env_path.write_text(text, encoding="utf-8")


def _write_mcp(installer: Installer) -> None:
    path = installer.root / "hermes_mcp_servers.json"
    snippet = {"mcp_servers": tool_runtime.mcp_config(root=str(installer.root))["mcp_servers"]}
    installer.record("write MCP config", ["write", str(path)])
    if not installer.dry_run:
        path.write_text(json.dumps(snippet, indent=2, sort_keys=True), encoding="utf-8")


def install(args: argparse.Namespace) -> dict:
    root = tool_runtime.chip_root(args.root)
    installer = Installer(root, args.dry_run)
    if not args.dry_run:
        root.mkdir(parents=True, exist_ok=True)
    installer.record("root", ["use", str(root)], skipped=root.exists())

    for name, spec in tool_runtime.REPO_SPECS.items():
        if name == "hermes-agent" and not args.include_hermes:
            continue
        _clone_repo(installer, name, spec)

    if args.mode == "full":
        _install_oss_cad_suite(installer)
        _build_opensta(installer, args.skip_opensta_build)

    _write_env(installer)
    _write_mcp(installer)
    report = tool_runtime.doctor(str(root))
    return {
        "ok": not installer.errors,
        "root": str(root),
        "dry_run": args.dry_run,
        "mode": args.mode,
        "actions": installer.actions,
        "errors": installer.errors,
        "doctor": report,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", default=None, help="Install root")
    parser.add_argument("--mode", choices=["minimal", "full"], default="minimal")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--include-hermes", action="store_true")
    parser.add_argument("--skip-opensta-build", action="store_true")
    parser.add_argument("--json", action="store_true", help="Print JSON")
    args = parser.parse_args()

    result = install(args)
    if args.json:
        print(json.dumps(result, indent=2, sort_keys=True))
    else:
        print(f"CktClaw chip toolchain root: {result['root']}")
        for action in result["actions"]:
            prefix = "skip" if action["skipped"] else "do"
            print(f"{prefix}: {action['action']} {' '.join(action['command'])}")
        if result["errors"]:
            print("Errors:", file=sys.stderr)
            for error in result["errors"]:
                print(f"- {error}", file=sys.stderr)
    return 0 if result["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
