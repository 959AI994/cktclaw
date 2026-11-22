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


def _print_rtl_llm_summary(console, result: Any, skill_name: str) -> None:
    from pathlib import Path

    from ..workflows.validated_rtl.observability import format_rtl_llm_cli_summary

    project_dir = None
    overall_status = ""
    if isinstance(result, list):
        for item in result:
            if not isinstance(item, dict):
                continue
            payload = item.get("result") if item.get("type") in {
                "chip_mission_result",
                "chip_autodesign_result",
            } else None
            if isinstance(payload, dict):
                overall_status = str(payload.get("status") or overall_status)
                project_dir = payload.get("project_dir") or project_dir
                if item.get("type") == "chip_mission_result" and payload.get("report_path"):
                    project_dir = str(Path(str(payload["report_path"])).parent)
    summary = format_rtl_llm_cli_summary(project_dir, overall_status=overall_status)
    if summary:
        console.print(f"[dim]{summary}[/dim]")


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
    rendered_text_parts: List[str] = []
    try:
        result = await skill.executor(effective_args, context)
    except Exception as e:
        console.print(f"[red]执行失败：{e}[/red]")
        return

    if isinstance(result, list):
        lines: List[str] = []
        for item in result:
            if isinstance(item, dict) and item.get("type") == "skill_doc":
                if "--show-skill-doc" not in effective_args:
                    console.print(
                        "[red]Refusing to print skill documentation during execution. "
                        "Use --show-skill-doc if you explicitly want the SKILL.md content.[/red]"
                    )
                    return
            if isinstance(item, dict) and "text" in item:
                text = str(item["text"])
                if (
                    "--show-skill-doc" not in effective_args
                    and skill.name == "erie-verilog-generator"
                    and text.startswith("# erie-verilog-generator")
                    and "Base directory for this skill" in text
                ):
                    console.print(
                        "[red]Misrouted erie-verilog-generator output detected (SKILL.md dump). "
                        "Execution handler should run ValidatedRTLController instead.[/red]"
                    )
                    return
                lines.append(text)
                rendered_text_parts.append(text)
            elif isinstance(item, dict) and item.get("type") in {
                "chip_mission_result",
                "chip_autodesign_result",
            }:
                continue
            elif isinstance(item, dict):
                text = str(item)
                lines.append(text)
                rendered_text_parts.append(text)
        if lines:
            console.print("\n\n".join(lines))
        if skill.name in {"chip-mission", "chip-autodesign"}:
            _print_rtl_llm_summary(console, result, skill.name)
    else:
        text = str(result)
        rendered_text_parts.append(text)
        console.print(text)

    # Persist workflow turns so follow-up free-form chat can summarize them.
    try:
        from ..cktmem import MessageRole, MessageType, ContextLayer

        user_content = f"/{skill_name} {effective_args}".strip()
        assistant_content = "\n\n".join(p for p in rendered_text_parts if p.strip())

        await cli_state.storage.add_message(
            session_id=cli_state.session_id,
            role=MessageRole.USER,
            content=user_content,
            msg_type=MessageType.CHAT,
            layer=ContextLayer.TURN,
        )
        await cli_state.storage.add_message(
            session_id=cli_state.session_id,
            role=MessageRole.ASSISTANT,
            content=assistant_content,
            msg_type=MessageType.CHAT,
            layer=ContextLayer.TURN,
        )
    except Exception as e:
        console.print(f"[yellow]⚠️ Failed to store workflow messages: {e}[/yellow]")
