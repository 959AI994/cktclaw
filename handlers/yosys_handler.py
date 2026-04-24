"""
Yosys Handler — /yosys command

Routes the ``/yosys`` REPL command to the YosysRunner and renders
the result with Rich panels.

- ``/yosys -p "read_verilog test.v; stat"``  → run directly
- ``/yosys``  (no args)                       → interactive fallback prompt
"""

from rich.console import Console
from rich.panel import Panel
from rich.text import Text
from rich.box import ROUNDED

from prompt_toolkit import PromptSession
from prompt_toolkit.formatted_text import HTML
from prompt_toolkit.completion import WordCompleter, PathCompleter, Completer, Completion

from ..eda_tools import YosysRunner
from ..eda_tools.tool_dicts import YOSYS_COMMANDS
from ..ui import render_spinner, render_error, Icons
from ..eda_tools.base_runner import clean_eda_output

# Reuse the shared rendering helpers from abc_handler
from .abc_handler import _persist_cli_turn, _prompt_for_script, _render_tool_output


# Module-level singleton
_yosys_runner = YosysRunner()


def handle_yosys(args: str, cli_state) -> None:
    """
    Entry point called by the REPL dispatcher.

    Args:
        args: Everything after ``/yosys `` (may be empty).
        cli_state: Global CLIState instance.
    """
    console: Console = cli_state.console

    # ── Interactive fallback when no args provided ──────────────
    if not args.strip():
        _interactive_builder(console, cli_state)
        return

    # ── Execute with spinner ───────────────────────────────────
    with render_spinner(console, f"{Icons.LIGHTNING} Running Yosys engine..."):
        result = _yosys_runner.run(args)

    # ── Render result ──────────────────────────────────────────
    if result.error:
        render_error(console, result.error, error_type="error")
        try:
            _persist_cli_turn(
                cli_state,
                f"[用户手动执行了 Yosys 脚本]:\n{args}",
                f"[Yosys 执行结果]:\n{result.error}",
            )
        except Exception:
            pass
        return

    # Memory integration (success)
    try:
        combined = (result.stdout or "").strip()
        if result.stderr and result.stderr.strip():
            combined = f"{combined}\n{result.stderr.strip()}".strip()
        cleaned = clean_eda_output("Yosys", combined)
        _persist_cli_turn(
            cli_state,
            f"[用户手动执行了 Yosys 脚本]:\n{args}",
            f"[Yosys 执行结果]:\n{cleaned or '(无输出)'}",
        )
    except Exception:
        pass

    _render_tool_output(console, result.stdout, result.stderr,
                        result.returncode, "Yosys")


def _interactive_builder(console: Console, cli_state) -> None:
    """
    Sub-REPL for Yosys: autocompletion + buffer + run/cancel.
    """
    words = list(YOSYS_COMMANDS.keys())
    meta = YOSYS_COMMANDS  # zh descriptions

    class HybridCompleter(Completer):
        def __init__(self):
            self.cmd = WordCompleter(words=words, meta_dict=meta, ignore_case=True)
            self.path = PathCompleter(expanduser=True)

        def get_completions(self, document, complete_event):
            text = document.text_before_cursor
            if " " not in text.strip():
                yield from self.cmd.get_completions(document, complete_event)
            else:
                yield from self.path.get_completions(document, complete_event)

    cmd_buffer: list[str] = []

    def get_toolbar():
        confirmed = " ; ".join(cmd_buffer)
        confirmed_html = f'<ansicyan>{confirmed}</ansicyan>' if confirmed else "(空)"
        return HTML(
            f'<style bg=\"ansiblack\" fg=\"ansiyellow\"> [当前脚本]: {confirmed_html}  '
            f'(输入示例: read_verilog ./test.v | 敲 run 执行，cancel 或 .. 回退) </style>'
        )

    cmd_completer = HybridCompleter()
    path_completer = PathCompleter(expanduser=True)
    session = PromptSession(complete_while_typing=True, bottom_toolbar=get_toolbar)

    def build_prompt():
        return HTML('<ansiyellow>CktClaw</ansiyellow> <ansigreen>[yosys]</ansigreen> ❯ ')

    while True:
        try:
            completer = cmd_completer
            if 'pending_cmd' not in locals():
                pending_cmd = ""
            if pending_cmd:
                placeholder = " <file_or_args> (示例: ./test.v)"
                prompt_message = build_prompt()
                completer = path_completer
            else:
                placeholder = " 选择命令或输入 .. 回退"
                prompt_message = build_prompt()

            user_line = session.prompt(prompt_message, completer=completer, placeholder=placeholder).strip()
        except (KeyboardInterrupt, EOFError):
            # Treat as cancel
            cmd_buffer.clear()
            console.print("[dim]已取消[/dim]")
            return

        if not user_line:
            continue

        # Backtrack support
        if user_line == ".." or user_line.lower().strip() == "cd ..":
            if pending_cmd:
                pending_cmd = ""
            elif cmd_buffer:
                cmd_buffer.pop()
            else:
                return
            continue

        # Auto-strip leading slash for accidental '/read_verilog ...'
        parts = user_line.split(None, 1)
        if parts:
            first = parts[0]
            if first.startswith("/") and first.find("/", 1) == -1:
                first = first[1:]
                user_line = f"{first} {parts[1]}" if len(parts) > 1 else first
                # 关键：去斜杠后需要重新计算 parts，避免后续校验仍读到旧值
                parts = user_line.split(None, 1)

        if not pending_cmd and user_line.lower() == "cancel":
            cmd_buffer.clear()
            console.print("[dim]已取消[/dim]")
            return

        if not pending_cmd and user_line.lower() == "run":
            script = " ; ".join(cmd_buffer)
            with render_spinner(console, f"{Icons.LIGHTNING} Running Yosys engine..."):
                result = _yosys_runner.run(script)
            if result.error:
                render_error(console, result.error, error_type="error")
                # Memory integration (error)
                try:
                    cli_state.memory_manager.add_message(
                        cli_state.session_id, "user", f"[用户手动执行了 Yosys 脚本]:\n{script}"
                    )
                    cli_state.memory_manager.add_message(
                        cli_state.session_id, "assistant", f"[Yosys 执行结果]:\n{result.error}"
                    )
                except Exception:
                    pass
                continue
            # Memory integration (success)
            try:
                combined = (result.stdout or "").strip()
                if result.stderr and result.stderr.strip():
                    combined = f"{combined}\n{result.stderr.strip()}".strip()
                cleaned = clean_eda_output("Yosys", combined)
                cli_state.memory_manager.add_message(
                    cli_state.session_id, "user", f"[用户手动执行了 Yosys 脚本]:\n{script}"
                )
                cli_state.memory_manager.add_message(
                    cli_state.session_id, "assistant", f"[Yosys 执行结果]:\n{cleaned or '(无输出)'}"
                )
            except Exception:
                pass
            _render_tool_output(console, result.stdout, result.stderr, result.returncode, "Yosys")
            # reset and continue
            cmd_buffer.clear()
            pending_cmd = ""
            continue

        if not pending_cmd:
            # Validate command token
            first_tok = (parts[0] if parts else user_line).strip()
            if first_tok not in YOSYS_COMMANDS and user_line.lower() not in ("run", "cancel"):
                console.print("[bold red]✗ 非法指令，请从菜单中选择或输入 .. 回退[/bold red]")
                continue
            if " " in user_line:
                cmd_buffer.append(user_line)
                continue
            pending_cmd = user_line
            continue
        else:
            if user_line:
                # Path existence hint (best-effort)
                import os
                token0 = user_line.split()[0]
                if token0.startswith(("/", "./", "../")) and not os.path.exists(token0):
                    console.print("[bold yellow]⚠️ 路径不存在，请重新输入或输入 .. 回退[/bold yellow]")
                    continue
                cmd_buffer.append(f"{pending_cmd} {user_line}")
            pending_cmd = ""
            continue
