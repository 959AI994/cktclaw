#!/usr/bin/env python3
"""Install this plugin into a Hermes Agent profile."""

from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

PLUGIN_NAME = "cktclaw-chip-design"
PLUGIN_ROOT = Path(__file__).resolve().parents[1]
HERMES_REPO = "https://github.com/NousResearch/hermes-agent.git"


def _default_hermes_home() -> Path:
    return Path(os.environ.get("HERMES_HOME", "~/.hermes")).expanduser()


def _run(command: list[str], dry_run: bool, actions: list[dict], cwd: Path | None = None) -> int:
    actions.append({"command": command, "cwd": str(cwd) if cwd else "", "dry_run": dry_run})
    if dry_run:
        return 0
    return subprocess.run(command, cwd=str(cwd) if cwd else None, check=False).returncode


def install(args: argparse.Namespace) -> dict:
    hermes_home = Path(args.hermes_home).expanduser().resolve()
    plugins_dir = hermes_home / "plugins"
    target = plugins_dir / PLUGIN_NAME
    actions: list[dict] = []
    errors: list[str] = []

    if args.clone_hermes:
        repo_dir = hermes_home / "hermes-agent"
        if not repo_dir.exists():
            rc = _run(["git", "clone", "--depth", "1", HERMES_REPO, str(repo_dir)], args.dry_run, actions)
            if rc != 0:
                errors.append(f"failed to clone Hermes Agent into {repo_dir}")

    actions.append({"command": ["mkdir", "-p", str(plugins_dir)], "cwd": "", "dry_run": args.dry_run})
    if not args.dry_run:
        plugins_dir.mkdir(parents=True, exist_ok=True)

    if target.exists() or target.is_symlink():
        if args.force:
            actions.append({"command": ["remove", str(target)], "cwd": "", "dry_run": args.dry_run})
            if not args.dry_run:
                if target.is_symlink() or target.is_file():
                    target.unlink()
                else:
                    shutil.rmtree(target)
        else:
            errors.append(f"target already exists: {target}; pass --force to replace")

    if not errors:
        if args.mode == "copy":
            actions.append({"command": ["copytree", str(PLUGIN_ROOT), str(target)], "cwd": "", "dry_run": args.dry_run})
            if not args.dry_run:
                shutil.copytree(PLUGIN_ROOT, target, ignore=shutil.ignore_patterns("__pycache__", "*.pyc"))
        else:
            actions.append({"command": ["ln", "-s", str(PLUGIN_ROOT), str(target)], "cwd": "", "dry_run": args.dry_run})
            if not args.dry_run:
                target.symlink_to(PLUGIN_ROOT, target_is_directory=True)

    if args.enable and not errors:
        hermes = shutil.which("hermes")
        if hermes or args.dry_run:
            rc = _run([hermes or "hermes", "plugins", "enable", PLUGIN_NAME], args.dry_run, actions)
            if rc != 0:
                errors.append("hermes plugins enable failed")
        else:
            errors.append("hermes command not found; install Hermes or enable the plugin manually")

    return {
        "ok": not errors,
        "plugin": PLUGIN_NAME,
        "plugin_source": str(PLUGIN_ROOT),
        "hermes_home": str(hermes_home),
        "target": str(target),
        "mode": args.mode,
        "actions": actions,
        "errors": errors,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--hermes-home", default=str(_default_hermes_home()))
    parser.add_argument("--mode", choices=["symlink", "copy"], default="symlink")
    parser.add_argument("--clone-hermes", action="store_true", help="Clone NousResearch/hermes-agent under the Hermes home if missing")
    parser.add_argument("--enable", action="store_true", help="Run hermes plugins enable cktclaw-chip-design")
    parser.add_argument("--force", action="store_true", help="Replace an existing plugin target")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    result = install(args)
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0 if result["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
