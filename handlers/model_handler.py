"""
Model Handler - /model command

Lightweight inline model selection with arrow-key navigation.
Uses Rich Live display + raw terminal input for a smooth interactive experience.

  ❯  💻 LogicRT   — 本地推理 ◀ 当前
     ☁️  DeepSeek  — 云端 API

  ↑↓ to move, Enter to confirm, Esc to cancel.
"""

import sys
import os
import tty
import termios
import select as _select

from rich.panel import Panel
from rich.box import ROUNDED
from rich.live import Live

from ..config import AVAILABLE_ENGINES
from ..ui import render_success, render_session_info


# ━━━━━━━━━━ Low-level Key Reader ━━━━━━━━━━
def _read_key():
    """
    Read a single keypress from stdin in raw mode.

    Handles:
      - Arrow keys (ESC [ A / B) → 'up' / 'down'
      - Enter                     → 'enter'
      - ESC (standalone)          → 'esc'
      - Ctrl+C                    → 'ctrl_c'

    Returns one of: 'up', 'down', 'enter', 'esc', 'ctrl_c', or None
    """
    fd = sys.stdin.fileno()
    old_settings = termios.tcgetattr(fd)
    try:
        tty.setraw(fd)
        ch = os.read(fd, 1)

        if ch == b'\x1b':
            # Might be an arrow-key escape sequence (\x1b [ A/B)
            # or a standalone ESC press.  Use select() with a short
            # timeout to distinguish.
            if _select.select([fd], [], [], 0.05)[0]:
                ch2 = os.read(fd, 1)
                if ch2 == b'[' and _select.select([fd], [], [], 0.05)[0]:
                    ch3 = os.read(fd, 1)
                    if ch3 == b'A':
                        return 'up'
                    if ch3 == b'B':
                        return 'down'
            return 'esc'

        if ch in (b'\r', b'\n'):
            return 'enter'
        if ch == b'\x03':          # Ctrl-C
            return 'ctrl_c'

        return None                # ignore everything else
    finally:
        termios.tcsetattr(fd, termios.TCSADRAIN, old_settings)


# ━━━━━━━━━━ Public API ━━━━━━━━━━
def select_model_interactive(cli_state) -> None:
    """
    Interactive model selection with arrow-key navigation.

    ↑/↓ moves the highlight, Enter confirms, Esc cancels.
    No numbers to type, no buttons to tab to.

    Args:
        cli_state: Global CLI state (CLIState instance)
    """
    console = cli_state.console
    current_engine = cli_state.current_engine

    # ── Build option list ──
    options = []  # [(engine_key, icon_name, description)]
    if "logicrt" in AVAILABLE_ENGINES:
        options.append(("logicrt", "💻 LogicRT", "本地推理，基于 CodeV，快速且隐私"))
    if "deepseek" in AVAILABLE_ENGINES:
        options.append(("deepseek", "☁️  DeepSeek", "云端 API，ByteDance Volcano Engine"))
    if "qwen" in AVAILABLE_ENGINES:
        options.append(("qwen", "🤖 Qwen", "本地推理，Qwen2.5-3B，轻量通用"))

    if not options:
        console.print("[red]没有可用的引擎 No engines available[/red]")
        return

    # Start with cursor on the current engine
    selected_idx = 0
    for i, (key, _, _) in enumerate(options):
        if key == current_engine:
            selected_idx = i

    # ── Renderable builder ──
    def _build_panel():
        lines = []
        for i, (key, name, desc) in enumerate(options):
            cur_tag = " [bold green]◀ 当前[/bold green]" if key == current_engine else ""
            if i == selected_idx:
                # Highlighted row
                lines.append(
                    f"  [bold cyan]❯[/bold cyan] [bold reverse] {name} [/bold reverse]"
                    f"  [bold]{desc}[/bold]{cur_tag}"
                )
            else:
                # Dim row
                lines.append(
                    f"    [dim]{name}[/dim]  [dim]{desc}[/dim]{cur_tag}"
                )

        return Panel(
            "\n".join(lines),
            title="[bold cyan]🔧 选择分析引擎 Engine Selection[/bold cyan]",
            subtitle="[dim]↑↓ 选择 · Enter 确认 · Esc 取消[/dim]",
            subtitle_align="center",
            border_style="cyan",
            box=ROUNDED,
            padding=(1, 2),
            expand=False,
        )

    # ── Interactive loop ──
    console.print()
    try:
        with Live(
            _build_panel(),
            console=console,
            auto_refresh=False,
            transient=True,       # menu disappears after selection
        ) as live:
            while True:
                key = _read_key()

                if key == 'up':
                    selected_idx = (selected_idx - 1) % len(options)
                    live.update(_build_panel(), refresh=True)

                elif key == 'down':
                    selected_idx = (selected_idx + 1) % len(options)
                    live.update(_build_panel(), refresh=True)

                elif key == 'enter':
                    break

                elif key in ('esc', 'ctrl_c'):
                    console.print("[yellow]已取消 Cancelled[/yellow]\n")
                    return

    except Exception:
        # Catch-all: any terminal weirdness → graceful cancel
        console.print("\n[yellow]已取消 Cancelled[/yellow]\n")
        return

    # ── Process selection ──
    selected_engine = options[selected_idx][0]

    # Same engine → no-op
    if selected_engine == current_engine:
        console.print(
            f"[dim]当前已使用 {_get_engine_display_name(selected_engine)}，无需切换。[/dim]\n"
        )
        return

    # Switch engine
    old_engine = current_engine
    cli_state.current_engine = selected_engine

    # Persist to database
    try:
        # Use cktmem storage instead of old memory_manager
        import asyncio
        asyncio.run(cli_state.storage.update_session(
            cli_state.session_id,
            model_choice=selected_engine
        ))
    except Exception as e:
        console.print(f"\n[red]✗ 会话更新失败: {e}[/red]\n")
        return

    # ── Success feedback ──
    console.print()
    render_success(
        console,
        f"引擎已切换: {_get_engine_display_name(old_engine)} → "
        f"{_get_engine_display_name(selected_engine)}",
        title="模型切换成功",
    )
    console.print()

    # Show engine details
    engine_details = {
        "当前引擎 Current": _get_engine_display_name(selected_engine).upper(),
        "前一个引擎 Previous": _get_engine_display_name(old_engine).upper(),
        "会话 Session": cli_state.session_id[:8],
    }
    if selected_engine == "deepseek":
        engine_details["API"] = "ByteDance Volcano Engine"
        engine_details["模型 Model"] = "DeepSeek V3"
        engine_details["类型 Type"] = "云端推理 Cloud"
    elif selected_engine == "qwen":
        engine_details["类型 Type"] = "本地推理 Local"
        engine_details["模型 Model"] = "Qwen2.5-3B"
        engine_details["设备 Device"] = "GPU"
    else:
        engine_details["类型 Type"] = "本地推理 Local"
        engine_details["模型 Model"] = "LogicRT (CodeV)"
        engine_details["设备 Device"] = "GPU"

    render_session_info(console, engine_details)


# ━━━━━━━━━━ Helpers ━━━━━━━━━━
def _get_engine_display_name(engine: str) -> str:
    """Get user-friendly display name for engine."""
    if engine == "logicrt":
        return "LogicRT"
    elif engine == "deepseek":
        return "DeepSeek"
    elif engine == "qwen":
        return "Qwen"
    return engine.upper()
