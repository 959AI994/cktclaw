"""
WrapperRunner — executes EDA tool wrapper scripts that emit structured JSON.
"""

import json
import subprocess
from pathlib import Path
from typing import Optional
from .base_runner import BaseRunner, RunResult

WRAPPERS_DIR = Path(__file__).parent / "wrappers"


class WrapperResult(RunResult):
    """RunResult extended with parsed JSON metrics from wrapper scripts."""
    status: str = ""
    summary: dict = None
    errors: list = None
    warnings: list = None

    def __init__(self, **kwargs):
        self.status = kwargs.pop("status", "")
        self.summary = kwargs.pop("summary", {})
        self.errors = kwargs.pop("errors", [])
        self.warnings = kwargs.pop("warnings", [])
        super().__init__(**kwargs)


class WrapperRunner(BaseRunner):
    """
    Runs a wrapper shell script and parses its JSON output.

    Wrapper scripts emit a single JSON object:
      {"tool": "...", "exit_code": 0, "status": "PASS",
       "summary": {...}, "errors": [...], "warnings": [...]}
    """

    wrapper_name: str = ""  # e.g. "wrap-yosys.sh"

    @property
    def wrapper_path(self) -> Path:
        return WRAPPERS_DIR / self.wrapper_name

    def is_available(self) -> bool:
        return self.wrapper_path.exists() and self.wrapper_path.is_file()

    def run(self, args: str, timeout: Optional[int] = None) -> WrapperResult:
        timeout = timeout or self.default_timeout

        if not self.is_available():
            return WrapperResult(
                returncode=-1,
                success=False,
                tool_name=self.tool_name,
                error=f"Wrapper script not found: {self.wrapper_path}",
            )

        cmd = [str(self.wrapper_path)] + (args.split() if args.strip() else [])
        try:
            proc = subprocess.run(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                timeout=timeout,
                text=True,
            )
            raw = proc.stdout.strip()
            try:
                data = json.loads(raw)
            except json.JSONDecodeError:
                data = {}

            return WrapperResult(
                returncode=proc.returncode,
                success=(proc.returncode == 0),
                stdout=raw,
                stderr=proc.stderr,
                tool_name=self.tool_name,
                command=" ".join(cmd),
                status=data.get("status", ""),
                summary=data.get("summary", {}),
                errors=data.get("errors", []),
                warnings=data.get("warnings", []),
            )
        except subprocess.TimeoutExpired:
            return WrapperResult(
                returncode=-1, success=False, tool_name=self.tool_name,
                error=f"{self.tool_name} wrapper timed out (>{timeout}s).",
            )
        except Exception as e:
            return WrapperResult(
                returncode=-1, success=False, tool_name=self.tool_name,
                error=f"{self.tool_name} wrapper error: {e}",
            )
