"""
ABC Handler — /abc command

Routes the ``/abc`` REPL command to the ABCRunner and renders
the result with Rich panels.

- ``/abc -c "read test.aig; print_stats"``  → run directly
- ``/abc``  (no args)                        → interactive fallback prompt
"""

import asyncio
import concurrent.futures

from rich.console import Console
from rich.panel import Panel
from rich.text import Text
from rich.box import ROUNDED

from prompt_toolkit import PromptSession
from prompt_toolkit.formatted_text import HTML
from prompt_toolkit.completion import WordCompleter, PathCompleter, Completer, Completion, NestedCompleter
from prompt_toolkit.key_binding import KeyBindings
from prompt_toolkit.styles import Style as PromptStyle

from ..eda_tools import ABCRunner
from ..eda_tools.base_runner import clean_eda_output
from ..ui import render_spinner, render_error, Icons


# ABC 常用指令（含中文注释与表情），围绕读取→结构化/优化→映射→时序/统计→导出
ABC_COMMANDS = {
    "read_aiger": "📥 读取 AIGER 格式电路 (.aig)",
    "read_verilog": "📥 读取 Verilog 格式电路 (.v)",
    "strash": "🏗️ 结构化 AIG (Structural Hashing)",
    "balance": "⚖️ AIG 树平衡 (Balance)",
    "rewrite": "🔄 AIG 重写优化 (Rewrite)",
    "refactor": "🔄 AIG 重构优化 (Refactor)",
    "topo": "📐 拓扑结构分析 (Topological Order)",
    "map": "🗺️ 工艺映射到标准单元 (Technology Mapping)",
    "stime": "⏱️ 静态时序分析 (Simple Timing Estimation)",
    "print_stats": "📊 打印电路统计 (PI/PO/Nodes/Levels)",
    "write_verilog": "📤 导出 Verilog 电路",
    "run": "🚀 执行当前积攒的 ABC 脚本",
    "..": "⬅️ 回退一级或返回主界面",
}

# Module-level singleton — avoids re-checking PATH every call
_abc_runner = ABCRunner()

def _persist_cli_turn(cli_state, user_text: str, assistant_text: str) -> None:
    """Persist a tool turn into cktmem storage for follow-up chat context."""
    if not getattr(cli_state, "storage", None):
        return

    async def _save():
        from ..cktmem import MessageRole, MessageType, ContextLayer
        await cli_state.storage.add_message(
            session_id=cli_state.session_id,
            role=MessageRole.USER,
            content=user_text,
            msg_type=MessageType.CHAT,
            layer=ContextLayer.TURN,
        )
        await cli_state.storage.add_message(
            session_id=cli_state.session_id,
            role=MessageRole.ASSISTANT,
            content=assistant_text,
            msg_type=MessageType.CHAT,
            layer=ContextLayer.TURN,
        )

    try:
        asyncio.run(_save())
    except RuntimeError:
        with concurrent.futures.ThreadPoolExecutor() as executor:
            future = executor.submit(asyncio.run, _save())
            future.result()


def handle_abc(args: str, cli_state) -> None:
    """
    Entry point called by the REPL dispatcher.

    Args:
        args: Everything after ``/abc `` (may be empty).
        cli_state: Global CLIState instance.
    """
    console: Console = cli_state.console

    # ── Interactive fallback when no args provided ──────────────
    if not args.strip():
        _interactive_builder(console, cli_state)
        return

    # ── Execute with spinner ───────────────────────────────────
    with render_spinner(console, f"{Icons.LIGHTNING} Running ABC engine..."):
        result = _abc_runner.run(args)

    # ── Render result ──────────────────────────────────────────
    if result.error:
        render_error(console, result.error, error_type="error")
        try:
            _persist_cli_turn(
                cli_state,
                f"[用户手动执行了 ABC 脚本]:\n{args}",
                f"[ABC 执行结果]:\n{result.error}",
            )
        except Exception:
            pass
        return

    # Memory integration (success)
    try:
        combined = (result.stdout or "").strip()
        if result.stderr and result.stderr.strip():
            combined = f"{combined}\n{result.stderr.strip()}".strip()
        cleaned = clean_eda_output("ABC", combined)
        _persist_cli_turn(
            cli_state,
            f"[用户手动执行了 ABC 脚本]:\n{args}",
            f"[ABC 执行结果]:\n{cleaned or '(无输出)'}",
        )
    except Exception:
        pass

    _render_tool_output(console, result.stdout, result.stderr,
                        result.returncode, "ABC")


# ━━━━━━━━━━ Shared helpers (used by both abc / yosys handlers) ━━━━━━━━━━

def _prompt_for_script(console: Console, tool_name: str) -> str:
    """
    Interactive fallback: ask the user for a command/script when
    they typed ``/abc`` or ``/yosys`` with no arguments.

    Returns the user input string, or empty string if cancelled.
    """
    console.print()


def _interactive_builder(console: Console, cli_state) -> None:
    """
    Sub-REPL for ABC: autocompletion + buffer + run/cancel.
    """
    words = list(ABC_COMMANDS.keys())
    meta = ABC_COMMANDS  # zh descriptions

    # Hybrid completer: first token → command list with meta; after space → file paths
    class HybridCompleter(Completer):
        def __init__(self):
            self.path = PathCompleter(expanduser=True)

        def get_completions(self, document, complete_event):
            text = (document.text_before_cursor or "")
            if " " not in text.strip():
                # Top-level command completion (prefix match, case-insensitive)
                raw = text.strip()
                # Treat leading '/' as part of trigger but not of the command token
                if raw.startswith("/"):
                    needle = raw[1:]
                else:
                    needle = raw
                for cmd, desc in ABC_COMMANDS.items():
                    if needle == "" or cmd.lower().startswith(needle.lower()):
                        # Replace the raw typed token (possibly starting with '/') with full cmd
                        yield Completion(cmd, start_position=-len(raw), display=cmd, display_meta=desc)
            else:
                # After first space, switch to path completion
                yield from self.path.get_completions(document, complete_event)

    cmd_buffer: list[str] = []
    # 层级状态：当前等待参数的子命令（如 'read_aiger'）
    current_sub_command: str = ""

    def get_toolbar():
        confirmed = " ; ".join(cmd_buffer)
        confirmed_html = f'<ansicyan>{confirmed}</ansicyan>' if confirmed else "(空)"
        return HTML(
            f'<style bg="ansiblack" fg="ansiyellow"> [当前脚本]: {confirmed_html}  '
            f'(输入示例: read_aiger ./test.aig | 敲 run 执行，cancel 或 .. 回退) </style>'
        )

    # Prepare session and completers; we'll swap completer per prompt call
    cmd_completer = HybridCompleter()
    path_completer = PathCompleter(expanduser=True)
    # Key bindings: force popup completion on '/' within ABC builder
    kb = KeyBindings()
    @kb.add('/')
    def _(event):
        event.app.current_buffer.insert_text('/')
        event.app.current_buffer.start_completion(select_first=False)
    # Local dark placeholder style to match global
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
            # 根据是否在子命令参数阶段，动态切换 Prompt 与 Completer
            if current_sub_command:
                # 子命令阶段：展示 [abc][sub] 并使用路径补全（适用文件参数的命令）
                prompt_message = HTML(f'<ansicyan>CktClaw</ansicyan> <ansigreen>[abc][{current_sub_command}]</ansigreen> ❯ ')
                if current_sub_command in ("read_aiger", "read_verilog", "write_verilog"):
                    completer = path_completer
                    placeholder = " <请输入文件路径或从下方选择>"
                else:
                    completer = cmd_completer
                    placeholder = " <请输入参数或从下方选择>"
                user_line = session.prompt(prompt_message, completer=completer, placeholder=placeholder).strip()
            else:
                # 顶层阶段：展示 [abc] 并使用命令补全
                prompt_message = HTML('<ansicyan>CktClaw</ansicyan> <ansigreen>[abc]</ansigreen> ❯ ')
                completer = cmd_completer
                user_line = session.prompt(prompt_message, completer=completer, placeholder=" 选择命令或输入 .. 回退").strip()
        except (KeyboardInterrupt, EOFError):
            # Treat as cancel
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
                # at root -> exit builder
                return
            continue

        # Auto-strip leading slash for accidental '/read_aiger ...'
        # Heuristic: if the first token begins with '/' and does not contain another '/',
        # treat it as a mistaken slash-command and strip the first '/'.
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
            # 如果脚本中没有任何会产生可视化输出的命令，则自动附加 print_stats 以避免“黑箱”
            lower_script = script.lower()
            has_reporter = any(tok in lower_script for tok in [
                "print_stats", "ps", "stime", "print ", "write_", "show", "ps;",
            ])
            if not has_reporter:
                script = f"{script} ; print_stats"
            with render_spinner(console, f"{Icons.LIGHTNING} Running ABC engine..."):
                result = _abc_runner.run(script)
            if result.error:
                render_error(console, result.error, error_type="error")
                # Memory integration (error)
                try:
                    cli_state.memory_manager.add_message(
                        cli_state.session_id, "user", f"[用户手动执行了 ABC 脚本]:\n{script}"
                    )
                    cli_state.memory_manager.add_message(
                        cli_state.session_id, "assistant", f"[ABC 执行结果]:\n{result.error}"
                    )
                except Exception:
                    pass
                # stay in builder
                continue
            # Memory integration (success)
            try:
                combined = (result.stdout or "").strip()
                if result.stderr and result.stderr.strip():
                    combined = f"{combined}\n{result.stderr.strip()}".strip()
                cleaned = clean_eda_output("ABC", combined)
                cli_state.memory_manager.add_message(
                    cli_state.session_id, "user", f"[用户手动执行了 ABC 脚本]:\n{script}"
                )
                cli_state.memory_manager.add_message(
                    cli_state.session_id, "assistant", f"[ABC 执行结果]:\n{cleaned or '(无输出)'}"
                )
            except Exception:
                pass
            _render_tool_output(console, result.stdout, result.stderr, result.returncode, "ABC")
            # reset state and continue
            cmd_buffer.clear()
            current_sub_command = ""
            continue

        # 层级两阶段：顶层选择命令 → 子命令输入参数
        if not current_sub_command:
            # Validate command token
            first_tok = parts[0] if parts else user_line
            if first_tok not in ABC_COMMANDS and user_line.lower() not in ("run", "cancel"):
                console.print("[bold red]✗ 非法指令，请从菜单中选择或输入 .. 回退[/bold red]")
                continue
            # 若为需要路径参数的命令，进入子命令状态，不立即入缓冲
            if first_tok in ("read_aiger", "read_verilog", "write_verilog", "map"):
                current_sub_command = first_tok
                continue
            # 其他：若含行内参数，直接入缓冲；否则仅记录命令本身
            if " " in user_line:
                cmd_buffer.append(user_line)
            else:
                cmd_buffer.append(first_tok)
            continue
        else:
            # 子命令参数阶段：当前输入为该命令的参数（路径/标志）
            # Warn for likely missing path
            import os
            token0 = user_line.split()[0]
            if token0.startswith(("/", "./", "../")) and not os.path.exists(token0):
                console.print("[bold yellow]⚠️ 路径不存在，请重新输入或输入 .. 回退[/bold yellow]")
                continue
            if user_line:
                cmd_buffer.append(f"{current_sub_command} {user_line}")
            # 自动回退到顶层
            current_sub_command = ""
            continue
    console.print(
        f"[bold yellow]{tool_name}[/bold yellow] — "
        f"请输入要执行的命令 (按 [bold]Enter[/bold] 提交, [bold]Ctrl+C[/bold] 取消):"
    )

    try:
        from rich.prompt import Prompt
        script = Prompt.ask(f"  [dim]{tool_name.lower()}>[/dim]")
        return script.strip()
    except (KeyboardInterrupt, EOFError):
        console.print("[dim]已取消[/dim]")
        return ""


def _render_tool_output(
    console: Console,
    stdout: str,
    stderr: str,
    returncode: int,
    tool_name: str,
) -> None:
    """
    Render captured stdout/stderr inside Rich panels.

    - stdout → main output panel (yellow border)
    - stderr → separate warning panel (red border, only if non-empty)
    - A one-line return-code summary at the end
    """
    console.print()

    # ── stdout ──────────────────────────────────────────────────
    merged = (stdout or "").strip()
    if not merged and not (stderr or "").strip():
        console.print(
            Panel(
                Text("⚠️ ABC 未返回任何标准输出，请检查命令是否正确。" if tool_name == "ABC" else "⚠️ 无标准输出"),
                title=f"[bold yellow]{tool_name} Output[/bold yellow]",
                title_align="left",
                border_style="yellow",
                box=ROUNDED,
                padding=(0, 1),
                expand=False,
            )
        )
    else:
        # Highlight ABC core stats like "i/o =" or "and ="
        if tool_name == "ABC" and merged:
            lines = merged.splitlines()
            txt = Text()
            for ln in lines:
                low = ln.lower()
                if "i/o" in low or "and" in low or "lev" in low:
                    txt.append(ln, style="bold cyan")
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

    # ── stderr (only when non-trivial) ─────────────────────────
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
