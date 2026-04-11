"""
Base Runner — generic subprocess executor for external EDA tools.

Captures stdout and stderr via subprocess.PIPE, enforces a configurable
timeout, and translates FileNotFoundError into a user-friendly message.
"""

import subprocess
import shutil
from dataclasses import dataclass, field
from typing import List, Optional


@dataclass
class RunResult:
    """Structured result of an EDA tool invocation."""

    # Exit status
    returncode: int = -1
    success: bool = False

    # Captured streams (decoded as UTF-8)
    stdout: str = ""
    stderr: str = ""

    # Metadata
    tool_name: str = ""
    command: str = ""

    # Error info (only set when the tool cannot be found or times out)
    error: Optional[str] = None


class BaseRunner:
    """
    Abstract base class for EDA tool runners.

    Subclasses must set ``tool_name`` and ``executable`` and may override
    ``build_command()`` to customise how CLI arguments are assembled.

    The main entry point is ``run(args)``, which:
    1. Builds the full command list via ``build_command(args)``.
    2. Spawns a subprocess with stdout/stderr piped.
    3. Waits up to ``timeout`` seconds.
    4. Returns a ``RunResult`` dataclass.
    """

    tool_name: str = "eda_tool"
    executable: str = "eda_tool"
    default_timeout: int = 120  # seconds

    # ------------------------------------------------------------------ #
    #  Public API                                                         #
    # ------------------------------------------------------------------ #

    def run(self, args: str, timeout: Optional[int] = None) -> RunResult:
        """
        Execute the tool with *args* (a single string of CLI arguments).

        Args:
            args: Raw argument string as the user typed it.
            timeout: Override for default_timeout (seconds).

        Returns:
            RunResult with captured stdout, stderr, and status.
        """
        timeout = timeout or self.default_timeout
        cmd = self.build_command(args)
        cmd_display = " ".join(cmd)

        # ── 1. Check tool availability ──────────────────────────────
        if not self.is_available():
            return RunResult(
                returncode=-1,
                success=False,
                tool_name=self.tool_name,
                command=cmd_display,
                error=(
                    f"LogicRT 找不到 [bold]{self.executable}[/bold] 命令，"
                    f"请确保该工具已安装并配置到了系统的环境变量 (PATH) 中。"
                ),
            )

        # ── 2. Run subprocess ───────────────────────────────────────
        try:
            proc = subprocess.run(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                timeout=timeout,
                text=True,
            )
            return RunResult(
                returncode=proc.returncode,
                success=(proc.returncode == 0),
                stdout=proc.stdout,
                stderr=proc.stderr,
                tool_name=self.tool_name,
                command=cmd_display,
            )

        except subprocess.TimeoutExpired:
            return RunResult(
                returncode=-1,
                success=False,
                tool_name=self.tool_name,
                command=cmd_display,
                error=f"{self.tool_name} 执行超时（>{timeout}s），已终止进程。",
            )

        except FileNotFoundError:
            return RunResult(
                returncode=-1,
                success=False,
                tool_name=self.tool_name,
                command=cmd_display,
                error=(
                    f"LogicRT 找不到 [bold]{self.executable}[/bold] 命令，"
                    f"请确保该工具已安装并配置到了系统的环境变量 (PATH) 中。"
                ),
            )

        except Exception as e:
            return RunResult(
                returncode=-1,
                success=False,
                tool_name=self.tool_name,
                command=cmd_display,
                error=f"{self.tool_name} 运行异常: {e}",
            )

    # ------------------------------------------------------------------ #
    #  Overrideable hooks                                                 #
    # ------------------------------------------------------------------ #

    def build_command(self, args: str) -> List[str]:
        """
        Assemble the full command list.

        Default implementation splits ``args`` via shell-like tokenisation.
        Subclasses may override for tool-specific argument handling.
        """
        import shlex
        return [self.executable] + shlex.split(args)

    def is_available(self) -> bool:
        """Return True if the executable is found on PATH."""
        return shutil.which(self.executable) is not None


# ───────────────────────── EDA Output Cleaner ───────────────────────── #
def clean_eda_output(tool_name: str, raw_output: str) -> str:
    """
    Remove noisy banners and footers from EDA tool outputs and keep core info.
    Rules:
      - Yosys: strip ASCII banners, license, git sha1, 'Time spent', 'End of script',
               'Logfile hash', box separators, and generic prompts.
      - ABC:   strip UC Berkeley / ABC copyright/version lines.
    Keep warnings, errors, statistics, and meaningful synthesis logs.
    """
    if not raw_output:
        return ""

    lines = raw_output.splitlines()
    cleaned = []

    # Common noise patterns (case-insensitive)
    common_drop = [
        r"^\s*/[-\\]{3,}\\s*$",     # ascii box top
        r"^\s*\\[-/]{3,}/\s*$",     # ascii box bottom
        r"^\s*-- Running command `help'\s*--\s*$",
        r"^\s*Type 'help.*$",
        r"^\s*End of script.*$",
        r"^\s*Logfile hash:.*$",
        r"^\s*Time spent:.*$",
    ]

    yosys_drop = [
        r"Yosys Open SYnthesis Suite",
        r"Copyright",
        r"Distributed under",
        r"git sha1",
        r"^\s*Yosys \d",  # version line
    ]

    abc_drop = [
        r"UC Berkeley",
        r"Berkeley Logic Synthesis",
        r"^\s*ABC\s+version.*$",
        r"^\s*compiled on.*$",
        r"^\s*usage:.*$",
    ]

    import re
    drop_patterns = [re.compile(pat, re.IGNORECASE) for pat in common_drop]
    if tool_name.lower().startswith("yosys"):
        drop_patterns += [re.compile(pat, re.IGNORECASE) for pat in yosys_drop]
    if tool_name.lower().startswith("abc"):
        drop_patterns += [re.compile(pat, re.IGNORECASE) for pat in abc_drop]

    for line in lines:
        text = line.rstrip()
        if not text:
            continue
        # Filter by patterns
        if any(p.search(text) for p in drop_patterns):
            continue
        cleaned.append(text)

    # Collapse excessive empty lines and join back
    result = "\n".join(cleaned).strip()
    return result
