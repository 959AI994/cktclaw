"""
Sessions Handler - 会话历史管理

提供会话列表查看、切换、删除等功能
"""

from typing import TYPE_CHECKING
from rich.console import Console
from rich.table import Table
from rich.panel import Panel
from datetime import datetime

if TYPE_CHECKING:
    from ..main import CLIState


async def handle_sessions(state: "CLIState", args: str = "") -> None:
    """
    处理 /sessions 命令

    功能：
    - /sessions: 列出所有历史会话
    - /sessions <session_id>: 切换到指定会话
    - /sessions delete <session_id>: 删除指定会话
    """
    console = Console()

    # 解析参数
    args = args.strip()

    if not args:
        # 列出所有会话
        await _list_sessions(state, console)
    elif args.startswith("delete "):
        # 删除会话
        session_id = args[7:].strip()
        await _delete_session(state, console, session_id)
    else:
        # 切换会话
        await _switch_session(state, console, args)


async def _list_sessions(state: "CLIState", console: Console) -> None:
    """列出所有会话"""
    sessions = await state.storage.list_sessions(limit=20)

    if not sessions:
        console.print(Panel(
            "📭 暂无历史会话",
            title="会话列表",
            border_style="yellow",
        ))
        return

    # 创建表格
    table = Table(
        title="📚 历史会话列表",
        show_header=True,
        header_style="bold cyan",
        border_style="blue",
    )

    table.add_column("Session ID", style="cyan", width=12)
    table.add_column("标题", style="green", width=30)
    table.add_column("项目", style="yellow", width=20)
    table.add_column("引擎", style="magenta", width=10)
    table.add_column("更新时间", style="white", width=19)
    table.add_column("压缩", style="red", width=6)

    current_session_id = state.session_id

    for session in sessions:
        session_id = session["session_id"]
        session_title = session.get("session_title") or "(无标题)"
        project_name = session.get("project_name") or "-"
        model_choice = session.get("model_choice", "logicrt")
        updated_at = session.get("updated_at", "")
        total_compactions = session.get("total_compactions", 0)

        # 格式化时间
        if updated_at:
            try:
                dt = datetime.fromisoformat(updated_at)
                updated_at = dt.strftime("%Y-%m-%d %H:%M:%S")
            except:
                pass

        # 截断显示
        session_id_display = session_id[:8] + "..."
        if len(session_title) > 30:
            session_title = session_title[:27] + "..."
        if len(project_name) > 20:
            project_name = project_name[:17] + "..."

        # 当前会话高亮
        if session_id == current_session_id:
            session_id_display = f"[bold green]→ {session_id_display}[/bold green]"

        table.add_row(
            session_id_display,
            session_title,
            project_name,
            model_choice,
            updated_at,
            str(total_compactions),
        )

    console.print(table)
    console.print("\n💡 提示:")
    console.print("  • /sessions <session_id> - 切换到指定会话")
    console.print("  • /sessions delete <session_id> - 删除指定会话")
    console.print("  • /clear - 创建新会话")


async def _switch_session(state: "CLIState", console: Console, session_id: str) -> None:
    """切换到指定会话"""
    # 支持短 ID 匹配
    if len(session_id) < 36:
        # 查找匹配的会话
        sessions = await state.storage.list_sessions(limit=100)
        matched = [s for s in sessions if s["session_id"].startswith(session_id)]

        if not matched:
            console.print(f"[red]✗[/red] 未找到会话: {session_id}")
            return
        elif len(matched) > 1:
            console.print(f"[yellow]⚠[/yellow] 找到多个匹配的会话，请提供更长的 ID:")
            for s in matched[:5]:
                console.print(f"  • {s['session_id'][:12]}... - {s.get('session_title', '(无标题)')}")
            return

        session_id = matched[0]["session_id"]

    # 验证会话是否存在
    session_info = await state.storage.get_session(session_id)
    if not session_info:
        console.print(f"[red]✗[/red] 会话不存在: {session_id}")
        return

    # 切换会话
    state.session_id = session_id
    state.project_name = session_info.get("project_name")
    state.model_choice = session_info.get("model_choice", "logicrt")

    session_title = session_info.get("session_title", "(无标题)")

    console.print(Panel(
        f"[green]✓[/green] 已切换到会话\n\n"
        f"Session ID: [cyan]{session_id[:8]}...[/cyan]\n"
        f"标题: [green]{session_title}[/green]\n"
        f"项目: [yellow]{state.project_name or '-'}[/yellow]\n"
        f"引擎: [magenta]{state.model_choice}[/magenta]",
        title="会话切换",
        border_style="green",
    ))


async def _delete_session(state: "CLIState", console: Console, session_id: str) -> None:
    """删除指定会话"""
    # 支持短 ID 匹配
    if len(session_id) < 36:
        sessions = await state.storage.list_sessions(limit=100)
        matched = [s for s in sessions if s["session_id"].startswith(session_id)]

        if not matched:
            console.print(f"[red]✗[/red] 未找到会话: {session_id}")
            return
        elif len(matched) > 1:
            console.print(f"[yellow]⚠[/yellow] 找到多个匹配的会话，请提供更长的 ID")
            return

        session_id = matched[0]["session_id"]

    # 验证会话是否存在
    session_info = await state.storage.get_session(session_id)
    if not session_info:
        console.print(f"[red]✗[/red] 会话不存在: {session_id}")
        return

    # 不能删除当前会话
    if session_id == state.session_id:
        console.print("[red]✗[/red] 不能删除当前会话，请先切换到其他会话")
        return

    # 确认删除
    from prompt_toolkit import prompt
    confirm = prompt(f"确认删除会话 {session_id[:8]}...? (yes/no): ")

    if confirm.lower() not in ["yes", "y"]:
        console.print("[yellow]已取消删除[/yellow]")
        return

    # 删除会话（通过 CASCADE 自动删除相关消息）
    import sqlite3
    conn = sqlite3.connect(state.storage.db_path)
    cursor = conn.cursor()
    cursor.execute("DELETE FROM sessions WHERE session_id = ?", (session_id,))
    conn.commit()
    conn.close()

    console.print(f"[green]✓[/green] 已删除会话: {session_id[:8]}...")
