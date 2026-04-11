"""
OpenSTA Handler — /opensta command

Routes the ``/opensta`` REPL command to the OpenSTARunner and renders
the result with Rich panels.

- ``/opensta -c "read_liberty lib.lib; report_checks"``  → run directly
- ``/opensta script.tcl``                                → run script file
- ``/opensta``  (no args)                                → interactive fallback prompt
"""

from rich.console import Console
from rich.panel import Panel
from rich.text import Text
from rich.box import ROUNDED

from prompt_toolkit import PromptSession
from prompt_toolkit.formatted_text import HTML
from prompt_toolkit.completion import WordCompleter, PathCompleter, Completer, Completion
from prompt_toolkit.key_binding import KeyBindings
from prompt_toolkit.styles import Style as PromptStyle

from ..eda_tools import OpenSTARunner
from ..eda_tools.base_runner import clean_eda_output
from ..ui import render_spinner, render_error, Icons


# OpenSTA 常用指令（含中文注释与表情）
OPENSTA_COMMANDS = {
    "read_liberty": "📥 读取 Liberty 时序库文件 (.lib)",
    "read_verilog": "📥 读取 Verilog 网表文件 (.v)",
    "read_sdc": "📥 读取 SDC 约束文件 (.sdc)",
    "link_design": "🔗 链接设计顶层模块",
    "create_clock": "🕐 创建时钟约束",
    "set_input_delay": "⏱️ 设置输入延迟约束",
    "set_output_delay": "⏱️ 设置输出延迟约束",
    "set_load": "⚡ 设置负载电容",
    "report_checks": "📊 报告时序路径检查",
    "report_worst_slack": "⚠️ 报告最差时序裕量",
    "report_tns": "📉 报告总负时序裕量 (TNS)",
    "report_wns": "📉 报告最差负时序裕量 (WNS)",
    "report_power": "🔋 报告功耗分析",
    "report_clock_skew": "🕐 报告时钟偏斜",
    "write_sdf": "📤 导出 SDF 延迟文件",
    "write_spef": "📤 导出 SPEF 寄生参数文件",
    "run": "🚀 执行当前积攒的 OpenSTA 脚本",
    "..": "⬅️ 回退一级或返回主界面",
}

# Module-level singleton
_opensta_runner = OpenSTARunner()


def handle_opensta(args: str, cli_state) -> None:
    """
    Entry point called by the REPL dispatcher.

    Args:
        args: Everything after ``/opensta `` (may be empty).
        cli_state: Global CLIState instance.
    """
    console: Console = cli_state.console

    # ── Interactive fallback when no args provided ──────────────
    if not args.strip():
        _interactive_builder(console, cli_state)
        return

    # ── Execute with spinner ───────────────────────────────────
    with render_spinner(console, f"{Icons.LIGHTNING} Running OpenSTA engine..."):
        result = _opensta_runner.run(args)

    # ── Render result ──────────────────────────────────────────
    if result.error:
        render_error(console, result.error, error_type="error")
        # Persist error to memory
        try:
            cli_state.memory_manager.add_message(
                cli_state.session_id, "user", f"[用户手动执行了 OpenSTA 脚本]:\n{args}"
            )
            cli_state.memory_manager.add_message(
                cli_state.session_id, "assistant", f"[OpenSTA 执行结果]:\n{result.error}"
            )
        except Exception:
            pass
        return

    # Memory integration (success)
    try:
        combined = (result.stdout or "").strip()
        if result.stderr and result.stderr.strip():
            combined = f"{combined}\n{result.stderr.strip()}".strip()
        cleaned = clean_eda_output("OpenSTA", combined)
        cli_state.memory_manager.add_message(
            cli_state.session_id, "user", f"[用户手动执行了 OpenSTA 脚本]:\n{args}"
        )
        cli_state.memory_manager.add_message(
            cli_state.session_id, "assistant", f"[OpenSTA 执行结果]:\n{cleaned or '(无输出)'}"
        )
    except Exception:
        pass

    _render_tool_output(console, result.stdout, result.stderr,
                        result.returncode, "OpenSTA")


def _interactive_builder(console: Console, cli_state) -> None:
    """
    Sub-REPL for OpenSTA: autocompletion + buffer + run/cancel.
    """
    words = list(OPENSTA_COMMANDS.keys())
    meta = OPENSTA_COMMANDS

    # Hybrid completer: first token → command list with meta; after space → file paths
    class HybridCompleter(Completer):
        def __init__(self):
            self.path = PathCompleter(expanduser=True)

        def get_completions(self, document, complete_event):
            text = (document.text_before_cursor or "")
            if " " not in text.strip():
                # Top-level command completion
                raw = text.strip()
                if raw.startswith("/"):
                    needle = raw[1:]
                else:
                    needle = raw
                for cmd, desc in OPENSTA_COMMANDS.items():
                    if needle == "" or cmd.lower().startswith(needle.lower()):
                        yield Completion(cmd, start_position=-len(raw), display=cmd, display_meta=desc)
            else:
                # After first space, switch to path completion
                yield from self.path.get_completions(document, complete_event)

    cmd_buffer: list[str] = []
    current_sub_command: str = ""

    def get_toolbar():
        confirmed = " ; ".join(cmd_buffer)
        confirmed_html = f'<ansicyan>{confirmed}</ansicyan>' if confirmed else "(空)"
        return HTML(
            f'<style bg="ansiblack" fg="ansiyellow"> [当前脚本]: {confirmed_html}  '
            f'(输入示例: read_liberty lib.lib | 敲 run 执行，cancel 或 .. 回退) </style>'
        )

    cmd_completer = HybridCompleter()
    path_completer = PathCompleter(expanduser=True)

    kb = KeyBindings()
    @kb.add('/')
    def _(event):
        event.app.current_buffer.insert_text('/')
        event.app.current_buffer.start_completion(select_first=False)

    cli_style_shim = PromptStyle.from_dict({
        'placeholder': 'fg:#222222 italic',
        'completion-menu': 'bg:default',
        'completion-menu.completion': 'fg:#56b6c2 bg:default',
        'completion-menu.completion.current': 'bg:#2c313a fg:#ffffff bold',
        'completion-menu.meta.completion': 'fg:#5c6370 bg:default',
        'completion-menu.meta.completion.current': 'bg:#2c313a fg:#abb2bf',
    })

    session = PromptSession(
        complete_while_typing=True,
        bottom_toolbar=get_toolbar,
        key_bindings=kb,
        style=cli_style_shim,
    )

    while True:
        try:
            if current_sub_command:
                prompt_message = HTML(f'<ansicyan>CktClaw</ansicyan> <ansigreen>[opensta][{current_sub_command}]</ansigreen> ❯ ')
                if current_sub_command in ("read_liberty", "read_verilog", "read_sdc", "write_sdf", "write_spef"):
                    completer = path_completer
                    placeholder = " <请输入文件路径或从下方选择>"
                else:
                    completer = cmd_completer
                    placeholder = " <请输入参数或从下方选择>"
                user_line = session.prompt(prompt_message, completer=completer, placeholder=placeholder).strip()
            else:
                prompt_message = HTML('<ansicyan>CktClaw</ansicyan> <ansigreen>[opensta]</ansigreen> ❯ ')
                completer = cmd_completer
                user_line = session.prompt(prompt_message, completer=completer, placeholder=" 选择命令或输入 .. 回退").strip()
        except (KeyboardInterrupt, EOFError):
            cmd_buffer.clear()
            console.print("[dim]已取消[/dim]")
            return

        if not user_line:
            continue

        # Backtrack support
        if user_line == ".." or user_line.lower().strip() == "cd ..":
            if current_sub_command:
                current_sub_command = ""
            elif cmd_buffer:
                cmd_buffer.pop()
            else:
                return
            continue

        # Auto-strip leading slash
        parts = user_line.split(None, 1)
        if parts:
            first = parts[0]
            if first.startswith("/") and first.find("/", 1) == -1:
                first = first[1:]
                user_line = f"{first} {parts[1]}" if len(parts) > 1 else first

        if not current_sub_command and user_line.lower() == "cancel":
            cmd_buffer.clear()
            console.print("[dim]已取消[/dim]")
            return
        if not current_sub_command and user_line.lower() in ("/exit", "exit"):
            raise SystemExit(0)

        if not current_sub_command and user_line.lower() == "run":
            script = " ; ".join(cmd_buffer).strip()
            # Auto-append report_checks if no reporting command present
            lower_script = script.lower()
            has_reporter = any(tok in lower_script for tok in [
                "report_", "write_", "show", "print",
            ])
            if not has_reporter:
                script = f"{script} ; report_checks"

            with render_spinner(console, f"{Icons.LIGHTNING} Running OpenSTA engine..."):
                result = _opensta_runner.run(script)

            if result.error:
                render_error(console, result.error, error_type="error")
                try:
                    cli_state.memory_manager.add_message(
                        cli_state.session_id, "user", f"[用户手动执行了 OpenSTA 脚本]:\n{script}"
                    )
                    cli_state.memory_manager.add_message(
                        cli_state.session_id, "assistant", f"[OpenSTA 执行结果]:\n{result.error}"
                    )
                except Exception:
                    pass
                continue

            # Memory integration (success)
            try:
                combined = (result.stdout or "").strip()
                if result.stderr and result.stderr.strip():
                    combined = f"{combined}\n{result.stderr.strip()}".strip()
                cleaned = clean_eda_output("OpenSTA", combined)
                cli_state.memory_manager.add_message(
                    cli_state.session_id, "user", f"[用户手动执行了 OpenSTA 脚本]:\n{script}"
                )
                cli_state.memory_manager.add_message(
                    cli_state.session_id, "assistant", f"[OpenSTA 执行结果]:\n{cleaned or '(无输出)'}"
                )
            except Exception:
                pass

            _render_tool_output(console, result.stdout, result.stderr, result.returncode, "OpenSTA")
            cmd_buffer.clear()
            current_sub_command = ""
            continue

        # Two-stage hierarchy
        if not current_sub_command:
            first_tok = parts[0] if parts else user_line
            if first_tok not in OPENSTA_COMMANDS and user_line.lower() not in ("run", "cancel"):
                console.print("[bold red]✗ 非法指令，请从菜单中选择或输入 .. 回退[/bold red]")
                continue

            # Commands that need file path parameters
            if first_tok in ("read_liberty", "read_verilog", "read_sdc", "write_sdf", "write_spef"):
                current_sub_command = first_tok
                continue

            # Other commands
            if " " in user_line:
                cmd_buffer.append(user_line)
            else:
                cmd_buffer.append(first_tok)
            continue
        else:
            # Sub-command parameter stage
            import os
            token0 = user_line.split()[0] if user_line.split() else user_line
            if token0.startswith(("/", "./", "../")) and not os.path.exists(token0):
                console.print("[bold yellow]⚠️ 路径不存在，请重新输入或输入 .. 回退[/bold yellow]")
                continue
            if user_line:
                cmd_buffer.append(f"{current_sub_command} {user_line}")
            current_sub_command = ""
            continue


def _render_tool_output(
    console: Console,
    stdout: str,
    stderr: str,
    returncode: int,
    tool_name: str,
) -> None:
    """
    Render captured stdout/stderr inside Rich panels.
    """
    console.print()

    # ── stdout ──────────────────────────────────────────────────
    merged = (stdout or "").strip()
    if not merged and not (stderr or "").strip():
        console.print(
            Panel(
                Text("⚠️ OpenSTA 未返回任何标准输出，请检查命令是否正确。"),
                title=f"[bold yellow]{tool_name} Output[/bold yellow]",
                title_align="left",
                border_style="yellow",
                box=ROUNDED,
                padding=(0, 1),
                expand=False,
            )
        )
    else:
        # Highlight timing-related keywords
        if tool_name == "OpenSTA" and merged:
            lines = merged.splitlines()
            txt = Text()
            for ln in lines:
                low = ln.lower()
                if any(kw in low for kw in ["slack", "delay", "arrival", "required", "clock", "setup", "hold"]):
                    txt.append(ln, style="bold cyan")
                elif "violation" in low or "fail" in low:
                    txt.append(ln, style="bold red")
                else:
                    txt.append(ln)
                txt.append("\n")
            content = txt
        else:
            content = Text(merged if merged else "(无输出 / no output)")

        console.print(
            Panel(
                content,
                title=f"[bold yellow]{tool_name} Output[/bold yellow]",
                title_align="left",
                border_style="yellow",
                box=ROUNDED,
                padding=(0, 1),
                expand=False,
            )
        )

    # ── stderr ─────────────────────────────────────────────────
    if stderr and stderr.strip():
        console.print(
            Panel(
                Text(stderr.strip()),
                title=f"[bold red]{tool_name} Stderr[/bold red]",
                title_align="left",
                border_style="red",
                box=ROUNDED,
                padding=(0, 1),
                expand=False,
            )
        )

    # ── Return code ────────────────────────────────────────────
    if returncode == 0:
        console.print(f"[bold green]✓ {tool_name} 执行完毕 (exit 0)[/bold green]")
    else:
        console.print(f"[bold red]✗ {tool_name} 返回码 {returncode}[/bold red]")

    console.print()
