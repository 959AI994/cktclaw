"""
Session Handler - /clear, /session, /sessions commands

Manages session lifecycle and persistence.
Provides session creation, metadata display, and session listing.
"""

import uuid
import asyncio
import os
from datetime import datetime

from ..ui import (
    render_error,
    render_success,
    render_session_info,
    render_divider,
    Icons,
)


def create_new_session(cli_state) -> None:
    """
    Create a new session and clear screen.

    Command: /clear

    Args:
        cli_state: Global CLI state (CLIState instance)
    """
    console = cli_state.console

    # Create new session
    try:
        old_session_id = cli_state.session_id

        # Generate new session ID
        new_session_id = uuid.uuid4().hex[:16]

        # Create in database using cktmem
        asyncio.run(
            cli_state.storage.create_session(
                session_id=new_session_id,
                project_name=os.path.basename(os.getcwd()),
                working_dir=os.getcwd(),
                model_choice=cli_state.current_engine,
            )
        )

        cli_state.session_id = new_session_id
        cli_state.current_aig_filename = None
        cli_state.last_verilog_code = None
        cli_state.last_analysis_report = None
        cli_state.aig_count = 0
        cli_state.chat_turns = 0

        # Context manager is already initialized, no need to rebuild

    except Exception as e:
        render_error(
            console,
            f"Failed to create new session: {e}",
            error_type="error",
        )
        return

    # Success message
    console.clear()
    console.print()

    render_success(
        console,
        f"New session created: {new_session_id[:8]}",
        title="Session Cleared",
    )
    console.print()


def handle_session_command(args: str, cli_state) -> None:
    """
    Handle /session subcommands.

    Commands:
    - /session info: Display current session metadata
    - /session export: Export session to JSON

    Args:
        args: Subcommand and arguments
        cli_state: Global CLI state (CLIState instance)
    """
    console = cli_state.console

    if not args.strip():
        render_error(
            console,
            "Usage: /session <info|export>",
            error_type="error",
        )
        return

    subcommand = args.strip().lower()

    if subcommand == "info":
        _display_session_info(cli_state)

    elif subcommand == "export":
        _export_session(cli_state)

    else:
        render_error(
            console,
            f"Unknown subcommand: /session {subcommand}. Available: info, export",
            error_type="error",
        )


def handle_sessions_command(args: str, cli_state) -> None:
    """
    Handle /sessions subcommands.

    Commands:
    - /sessions: List recent sessions (default)
    - /sessions list: List recent sessions
    - /sessions delete <session_id>: Delete a session
    - /sessions clear: Delete all non-current sessions in current project (requires DELETE confirmation)
    - /sessions <session_id>: Switch to a session

    Args:
        args: Subcommand and arguments
        cli_state: Global CLI state (CLIState instance)
    """
    console = cli_state.console

    if not args.strip():
        # Default: list sessions
        _list_sessions(cli_state, limit=20)
        return

    parts = args.strip().split(maxsplit=1)
    subcommand = parts[0].lower()
    extra_args = parts[1] if len(parts) > 1 else ""

    if subcommand == "list":
        _list_sessions(cli_state, limit=20)

    elif subcommand == "clear":
        _clear_sessions(cli_state)

    elif subcommand == "delete":
        if not extra_args:
            render_error(
                console,
                "Usage: /sessions delete <session_id>",
                error_type="error",
            )
            return
        _delete_session(extra_args, cli_state)

    else:
        # Try to switch to session by ID
        _switch_session(subcommand, cli_state)


# ━━━━━━━━━━ Helper Functions ━━━━━━━━━━
def _display_session_info(cli_state) -> None:
    """Display current session metadata."""
    console = cli_state.console

    try:
        # Get session data using cktmem
        session_data = asyncio.run(
            cli_state.storage.get_session(cli_state.session_id)
        )

        if not session_data:
            render_error(
                console,
                f"Session not found: {cli_state.session_id}",
                error_type="error",
            )
            return

        # Get context stats
        stats = asyncio.run(
            cli_state.context_manager.get_context_stats(cli_state.session_id)
        )

        # Prepare display data
        display_data = {
            "session_id": cli_state.session_id,
            "created_at": session_data.get("created_at", "N/A"),
            "project_name": session_data.get("project_name") or "(none)",
            "model_choice": session_data.get("model_choice", "unknown"),
            "messages": stats.get("total_messages", 0),
            "tokens": stats.get("total_tokens", 0),
            "compactions": stats.get("total_compactions", 0),
            "aig_count": cli_state.aig_count,
            "chat_turns": cli_state.chat_turns,
        }

        console.print()
        render_session_info(console, display_data)
        console.print()

    except Exception as e:
        render_error(
            console,
            f"Failed to retrieve session info: {e}",
            error_type="error",
        )


def _list_sessions(cli_state, limit: int = 10) -> None:
    """List recent sessions from database."""
    console = cli_state.console

    try:
        conn = cli_state.storage._get_connection()

        # Query recent sessions with title
        rows = conn.execute(
            """SELECT session_id, created_at, updated_at, project_name, model_choice, session_title, total_compactions
               FROM sessions
               ORDER BY updated_at DESC
               LIMIT ?""",
            (limit,),
        ).fetchall()

        conn.close()

        if not rows:
            console.print("[dim]No sessions found[/dim]")
            return

        from rich.table import Table

        table = Table(
            title=f"📚 历史会话列表 (最近 {len(rows)} 个)",
            show_header=True,
            header_style="bold cyan",
            border_style="blue",
        )

        table.add_column("ID", style="cyan", width=10)
        table.add_column("标题", style="green", width=30)
        table.add_column("项目", style="yellow", width=15)
        table.add_column("引擎", style="magenta", width=8)
        table.add_column("更新时间", style="white", width=16)
        table.add_column("压缩", style="red", width=4)

        for row in rows:
            session_id = row[0]
            created_at = row[1]
            updated_at = row[2] or created_at
            project_name = row[3] or "-"
            model_choice = row[4]
            session_title = row[5] or "(无标题)"
            total_compactions = row[6] or 0

            # Highlight current session
            session_id_display = session_id[:8]
            if session_id == cli_state.session_id:
                session_id_display = f"[bold green]→ {session_id_display}[/bold green]"

            # Truncate long strings
            if len(session_title) > 30:
                session_title = session_title[:27] + "..."
            if len(project_name) > 15:
                project_name = project_name[:12] + "..."

            # Format time
            time_display = updated_at[:16] if updated_at else created_at[:16]

            table.add_row(
                session_id_display,
                session_title,
                project_name,
                model_choice,
                time_display,
                str(total_compactions),
            )

        console.print()
        console.print(table)
        console.print()
        console.print("[dim]💡 提示:[/dim]")
        console.print("[dim]  • /sessions 96e36f87 - 切换到指定会话（直接输入ID，不要尖括号）[/dim]")
        console.print("[dim]  • /sessions delete 96e36f87 - 删除指定会话[/dim]")
        console.print("[dim]  • /sessions clear - 删除当前项目下除当前会话外的全部会话[/dim]")
        console.print()

    except Exception as e:
        render_error(
            console,
            f"Failed to list sessions: {e}",
            error_type="error",
        )


def _switch_session(session_id_prefix: str, cli_state) -> None:
    """Switch to a different session by ID prefix."""
    console = cli_state.console

    try:
        conn = cli_state.storage._get_connection()

        # Find sessions matching the prefix
        rows = conn.execute(
            """SELECT session_id, session_title, project_name, model_choice
               FROM sessions
               WHERE session_id LIKE ?
               ORDER BY updated_at DESC
               LIMIT 10""",
            (f"{session_id_prefix}%",),
        ).fetchall()

        conn.close()

        if not rows:
            render_error(
                console,
                f"未找到会话: {session_id_prefix}",
                error_type="error",
            )
            return

        if len(rows) > 1:
            console.print(f"[yellow]⚠[/yellow] 找到多个匹配的会话，请提供更长的 ID:")
            for row in rows[:5]:
                sid = row[0]
                title = row[1] or "(无标题)"
                console.print(f"  • {sid[:12]}... - {title}")
            return

        # Switch to the session
        session_id = rows[0][0]
        session_title = rows[0][1] or "(无标题)"
        project_name = rows[0][2]
        model_choice = rows[0][3]

        cli_state.session_id = session_id
        cli_state.project_name = project_name
        cli_state.model_choice = model_choice

        from rich.panel import Panel
        console.print()
        console.print(Panel(
            f"[green]✓[/green] 已切换到会话\n\n"
            f"Session ID: [cyan]{session_id[:8]}...[/cyan]\n"
            f"标题: [green]{session_title}[/green]\n"
            f"项目: [yellow]{project_name or '-'}[/yellow]\n"
            f"引擎: [magenta]{model_choice}[/magenta]",
            title="会话切换",
            border_style="green",
        ))
        console.print()

    except Exception as e:
        render_error(
            console,
            f"Failed to switch session: {e}",
            error_type="error",
        )


def _export_session(cli_state) -> None:
    """Export current session to JSON file."""
    console = cli_state.console

    try:
        import json
        from pathlib import Path

        # Get all messages using cktmem
        messages = asyncio.run(
            cli_state.storage.get_messages(cli_state.session_id)
        )

        # Get session metadata
        session_data = asyncio.run(
            cli_state.storage.get_session(cli_state.session_id)
        )

        # Convert messages to dict format
        messages_dict = [
            {
                "role": msg.role.value if hasattr(msg.role, 'value') else msg.role,
                "content": msg.content,
                "msg_type": msg.msg_type.value if hasattr(msg.msg_type, 'value') else msg.msg_type,
                "layer": msg.layer.value if hasattr(msg.layer, 'value') else msg.layer,
                "created_at": msg.created_at.isoformat(),
            }
            for msg in messages
        ]

        # Prepare export data
        export_data = {
            "session_id": cli_state.session_id,
            "created_at": session_data.get("created_at"),
            "project_name": session_data.get("project_name"),
            "model_choice": session_data.get("model_choice"),
            "messages": messages_dict,
        }

        # Write to file
        export_file = Path(f"session_{cli_state.session_id[:8]}.json")
        with open(export_file, "w") as f:
            json.dump(export_data, f, indent=2)

        render_success(
            console,
            f"Session exported to {export_file}",
            title="Export Complete",
        )

    except Exception as e:
        render_error(
            console,
            f"Failed to export session: {e}",
            error_type="error",
        )


def _delete_session(session_id: str, cli_state) -> None:
    """Delete a session via CktMem Storage (legacy MemoryManager is no longer used)."""
    console = cli_state.console

    if cli_state.storage is None:
        render_error(
            console,
            "Storage not initialized",
            error_type="error",
        )
        return

    raw = session_id.strip()

    try:
        conn = cli_state.storage._get_connection()

        rows = conn.execute(
            """SELECT session_id, session_title FROM sessions
               WHERE session_id LIKE ?
               ORDER BY updated_at DESC
               LIMIT 10""",
            (f"{raw}%",),
        ).fetchall()

        conn.close()

        if not rows:
            render_error(
                console,
                f"未找到会话: {raw}",
                error_type="error",
            )
            return

        if len(rows) > 1:
            console.print("[yellow]⚠[/yellow] 找到多个匹配的会话，请提供更长的 ID:")
            for row in rows[:5]:
                sid = row[0]
                title = row[1] or "(无标题)"
                console.print(f"  • {sid[:12]}... - {title}")
            return

        full_id = rows[0][0]

        if full_id == cli_state.session_id:
            render_error(
                console,
                "Cannot delete current session",
                error_type="error",
            )
            return

        ok = asyncio.run(cli_state.storage.delete_session(full_id))
        if not ok:
            render_error(
                console,
                f"未能删除会话: {full_id}",
                error_type="error",
            )
            return

        render_success(
            console,
            f"Session deleted: {full_id[:8]}...",
            title="Deletion Complete",
        )

    except Exception as e:
        render_error(
            console,
            f"Failed to delete session: {e}",
            error_type="error",
        )


def _clear_sessions(cli_state) -> None:
    """
    Delete all non-current sessions for the current project.

    Requires explicit "DELETE" confirmation to avoid accidental data loss.
    """
    console = cli_state.console

    if cli_state.storage is None:
        render_error(console, "Storage not initialized", error_type="error")
        return

    project_name = os.path.basename(os.getcwd())
    current_session = cli_state.session_id

    try:
        conn = cli_state.storage._get_connection()
        rows = conn.execute(
            """SELECT session_id FROM sessions
               WHERE project_name = ? AND session_id != ?""",
            (project_name, current_session),
        ).fetchall()
        conn.close()
    except Exception as e:
        render_error(console, f"Failed to query sessions: {e}", error_type="error")
        return

    if not rows:
        console.print("[dim]No deletable sessions found for current project.[/dim]")
        return

    count = len(rows)
    console.print(
        f"[yellow]About to delete {count} sessions for project '{project_name}' "
        f"(excluding current session {current_session[:8]}...).[/yellow]"
    )

    try:
        from prompt_toolkit import prompt
        confirm = prompt("Type DELETE to continue: ").strip()
    except (KeyboardInterrupt, EOFError):
        console.print("[yellow]Cancelled.[/yellow]")
        return

    if confirm != "DELETE":
        console.print("[yellow]Cancelled. No sessions were deleted.[/yellow]")
        return

    deleted = 0
    for row in rows:
        sid = row[0]
        try:
            ok = asyncio.run(cli_state.storage.delete_session(sid))
            if ok:
                deleted += 1
        except Exception:
            continue

    render_success(
        console,
        f"Deleted {deleted}/{count} sessions for project '{project_name}'.",
        title="Sessions Cleared",
    )
