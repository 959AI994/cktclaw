"""
Workflow Skill CLI — /rltf、/pareto-negotiate 等

由 Harness Skill 注册表调度 workflows 下的 RLTF、Pareto Negotiation 等能力。
无参数时与 /reverse 类似：进入交互式路径补全，避免直接报错。
"""

import os
from typing import Any, Dict, List, Optional

from prompt_toolkit import PromptSession
from prompt_toolkit.completion import PathCompleter
from prompt_toolkit.formatted_text import HTML
from prompt_toolkit.styles import Style as PromptStyle

from ..harness import get_skill_registry
from ..harness.skills.skill_registry import SkillNotFoundError


async def _prompt_aig_path_if_missing(console, bracket_label: str) -> Optional[str]:
    """
    无参时提示用户选择 .aig 路径（PathCompleter）。
    输入 .. / /back 取消；Ctrl+C 取消；exit 退出程序。
    """
    style_shim = PromptStyle.from_dict({
        "placeholder": "fg:#222222 italic",
        "completion-menu": "bg:default",
        "completion-menu.completion": "fg:#56b6c2 bg:default",
        "completion-menu.completion.current": "bg:#2c313a fg:#ffffff bold",
        "completion-menu.meta.completion": "fg:#5c6370 bg:default",
        "completion-menu.meta.completion.current": "bg:#2c313a fg:#abb2bf",
    })
    session = PromptSession(complete_while_typing=True, style=style_shim)

    while True:
        try:
            text = (
                await session.prompt_async(
                    HTML(
                        f"<ansicyan>CktClaw</ansicyan> "
                        f"<ansigreen>[{bracket_label}]</ansigreen> ❯ "
                    ),
                    completer=PathCompleter(expanduser=True),
                    placeholder=" <请选择 .aig 文件路径>",
                )
            ).strip()
        except (KeyboardInterrupt, EOFError):
            return None

        if not text:
            continue

        raw = text.strip()
        if raw in ("..", "cd ..", "/back"):
            return None
        if raw in ("/exit", "exit"):
            raise SystemExit(0)

        if not os.path.exists(raw):
            console.print(
                "[bold yellow]⚠️ 路径不存在，请重新输入或输入 .. 返回主界面[/bold yellow]"
            )
            continue

        return raw


async def process_workflow_skill(skill_name: str, args: str, cli_state) -> None:
    """
    执行已注册的 workflow 类技能（名称或别名均可）。

    Args:
        skill_name: 技能主名，如 rltf、pareto-negotiate
        args: 传给技能执行器的参数字符串
        cli_state: 全局 CLI 状态
    """
    console = cli_state.console
    registry = get_skill_registry()

    try:
        skill = await registry.get_skill(skill_name)
    except SkillNotFoundError as e:
        console.print(f"[yellow]⚠️ {e}[/yellow]")
        console.print(
            "[dim]若启动时曾提示技能注册失败，请检查依赖（如 openai）与日志。[/dim]"
        )
        return

    if not skill.executor:
        console.print(f"[red]技能 '{skill.name}' 未配置执行器。[/red]")
        return

    effective_args = args.strip()
    if not effective_args and skill_name in ("rltf", "pareto-negotiate"):
        bracket = "rltf" if skill_name == "rltf" else "pareto-negotiate"
        picked = await _prompt_aig_path_if_missing(console, bracket)
        if picked is None:
            console.print("[dim]已取消。[/dim]")
            return
        effective_args = picked

    context: Dict[str, Any] = {"cli_state": cli_state}
    try:
        result = await skill.executor(effective_args, context)
    except Exception as e:
        console.print(f"[red]执行失败：{e}[/red]")
        return

    if isinstance(result, list):
        lines: List[str] = []
        for item in result:
            if isinstance(item, dict) and "text" in item:
                lines.append(str(item["text"]))
            elif isinstance(item, dict):
                lines.append(str(item))
        if lines:
            console.print("\n\n".join(lines))
        return

    console.print(str(result))
