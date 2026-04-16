"""
Chip Design Handler — routes /chip-* commands to the corresponding domain skills.
"""

import asyncio
import re
from typing import Any, Dict, List, Optional, Tuple

from rich.console import Console
from rich.panel import Panel
from rich.markdown import Markdown
from prompt_toolkit import PromptSession
from prompt_toolkit.formatted_text import HTML
from prompt_toolkit.completion import WordCompleter
from prompt_toolkit.key_binding import KeyBindings
from prompt_toolkit.styles import Style as PromptStyle

from .. import config
from ..harness import get_skill_registry
from ..harness.skills.skill_registry import SkillNotFoundError


def _chip_domain_completer() -> WordCompleter:
    meta = {f"/{p}": f"🔷 {blurb}" for p, blurb in config.CHIP_DESIGN_SLASH_ROWS}
    pad = max(22, max(len(c) for c in meta) + 2)
    words = [c.ljust(pad) for c in meta]
    meta_padded = {c.ljust(pad): d for c, d in meta.items()}
    slash_pattern = re.compile(r'(/[\w-]*)')
    return WordCompleter(
        words=words,
        meta_dict=meta_padded,
        pattern=slash_pattern,
        sentence=True,
        match_middle=False,
        ignore_case=False,
    )


def _parse_first_slash_cmd(line: str) -> Tuple[Optional[str], str]:
    line = line.strip()
    if not line.startswith("/"):
        return None, line
    parts = line.split(maxsplit=1)
    cmd = parts[0].lstrip("/").lower()
    rest = parts[1] if len(parts) > 1 else ""
    return cmd, rest


def _prompt_bracket_chip_design_skills() -> HTML:
    return HTML(
        "<ansicyan>CktClaw</ansicyan>"
        "<ansigreen>[chip-design-skills]</ansigreen>"
        "<ansigray>></ansigray> "
    )


def _prompt_bracket_nested(skill_name: str) -> HTML:
    return HTML(
        "<ansicyan>CktClaw</ansicyan>"
        "<ansigreen>[chip-design-skills]</ansigreen>"
        f"<ansigreen>[{skill_name}]</ansigreen>"
        "<ansigray>></ansigray> "
    )


async def show_chip_design_menu(cli_state) -> None:
    """打印 /chip-* 子命令列表。"""
    console = cli_state.console
    lines = [
        "### 芯片设计子命令",
        "",
        "在 **`[chip-design-skills]`** 提示符下选择领域；进入二级后输入自然语言任务。",
        "输入 **`..`** 返回上一级或主界面。",
        "",
    ]
    for primary, blurb in config.CHIP_DESIGN_SLASH_ROWS:
        lines.append(f"- **`/{primary}`** — {blurb}")
    text = "\n".join(lines)
    console.print(
        Panel(
            Markdown(text),
            title="[bold cyan]Chip design skills[/bold cyan]",
            border_style="cyan",
        )
    )


def handle_chip_design_skills(args: str, cli_state) -> None:
    """
    /chip-design-skills：进入芯片设计子 REPL（与 /abc、/opensta 相同模式）。
    提示符：CktClaw[chip-design-skills]> → CktClaw[chip-design-skills][chip-xxx]>
    """
    console: Console = cli_state.console
    asyncio.run(show_chip_design_menu(cli_state))

    cli_style = PromptStyle.from_dict({
        "completion-menu.completion": "fg:#56b6c2",
        "completion-menu.completion.current": "fg:#ffffff bold",
        "completion-menu.meta.completion": "fg:#5c6370",
        "completion-menu.meta.completion.current": "fg:#abb2bf",
    })
    kb = KeyBindings()

    @kb.add("/")
    def _(event):
        event.app.current_buffer.insert_text("/")
        event.app.current_buffer.start_completion(select_first=False)

    session = PromptSession(
        completer=_chip_domain_completer(),
        complete_while_typing=True,
        key_bindings=kb,
        style=cli_style,
        mouse_support=False,
    )

    p1 = _prompt_bracket_chip_design_skills()

    while True:
        try:
            line = session.prompt(
                p1,
                placeholder=" /chip-synthesis 等，.. 返回主界面",
            ).strip()
        except (KeyboardInterrupt, EOFError):
            console.print("[dim]已退出芯片设计子终端[/dim]")
            return

        if not line:
            continue
        if line == ".." or line.lower() == "cd ..":
            console.print("[dim]已返回 CktClaw 主界面[/dim]")
            return

        cmd, rest = _parse_first_slash_cmd(line)
        if cmd is None:
            console.print("[yellow]请以 /chip- 开头选择子领域[/yellow]")
            continue
        if cmd == "chip-design-skills":
            console.print("[dim]已在芯片设计子终端内；输入 .. 返回主界面[/dim]")
            continue
        if cmd not in config.CHIP_DESIGN_SKILL_NAMES:
            console.print(
                f"[yellow]未知命令 /{cmd}。请从列表中选择 /chip-*。[/yellow]"
            )
            continue

        skill_name = cmd
        task = rest.strip()

        if not task:
            p2 = _prompt_bracket_nested(skill_name)
            try:
                task = session.prompt(
                    p2,
                    placeholder=" 自然语言描述任务，.. 回退到选领域",
                ).strip()
            except (KeyboardInterrupt, EOFError):
                console.print("[dim]已取消[/dim]")
                continue
            if not task:
                continue
            if task == ".." or task.lower() == "cd ..":
                continue

        asyncio.run(handle_chip_design(skill_name, task, cli_state))


async def handle_chip_design(skill_name: str, args: str, cli_state) -> None:
    """
    Execute a chip design domain skill by name.

    Args:
        skill_name: One of chip-architecture, chip-rtl, chip-verification, etc.
        args: Arguments passed by the user
        cli_state: Global CLI state
    """
    console = cli_state.console
    registry = get_skill_registry()

    try:
        skill = await registry.get_skill(skill_name)
    except SkillNotFoundError:
        console.print(f"[yellow]⚠️ Skill '{skill_name}' not found. Run /help for available commands.[/yellow]")
        return

    if not skill.executor:
        console.print(f"[red]Skill '{skill.name}' has no executor configured.[/red]")
        return

    context: Dict[str, Any] = {"cli_state": cli_state}
    try:
        result = await skill.executor(args.strip(), context)
    except Exception as e:
        console.print(f"[red]Error executing {skill.display_name}: {e}[/red]")
        return

    if isinstance(result, list):
        for item in result:
            if isinstance(item, dict) and "text" in item:
                text = item["text"]
                console.print(
                    Panel(
                        Markdown(text),
                        title=f"[bold cyan]{skill.display_name or skill.name}[/bold cyan]",
                        border_style="cyan",
                    )
                )
        return

    console.print(str(result))
