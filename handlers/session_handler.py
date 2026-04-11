"""
Session Handler - /clear, /session, /sessions commands

Manages session lifecycle and persistence.
Provides session creation, metadata display, and session listing.
"""

import uuid
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

        # Create in database
        new_session_id = cli_state.memory_manager.create_session(
            aig_filename="",
            model_choice=cli_state.current_engine,
        )

        cli_state.session_id = new_session_id
        cli_state.current_aig_filename = None
        cli_state.last_verilog_code = None
        cli_state.last_analysis_report = None
        cli_state.aig_count = 0
        cli_state.chat_turns = 0

        # Rebuild context builder for new session
        from webapp.backend.models.llm_analyzer import LLMVerilogAnalyzer
        from webapp.memory.context_builder import ContextBuilder

        system_prompt = LLMVerilogAnalyzer.LOGICRT_SYSTEM_PROMPT
        cli_state.context_builder = ContextBuilder(
            cli_state.memory_manager,
            system_prompt,
            max_rounds=cli_state.max_memory_rounds,
        )

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
    - /sessions list: List recent sessions
    - /sessions delete <session_id>: Delete a session

    Args:
        args: Subcommand and arguments
        cli_state: Global CLI state (CLIState instance)
    """
    console = cli_state.console

    if not args.strip():
        render_error(
            console,
            "Usage: /sessions <list|delete>",
            error_type="error",
        )
        return

    parts = args.strip().split(maxsplit=1)
    subcommand = parts[0].lower()
    extra_args = parts[1] if len(parts) > 1 else ""

    if subcommand == "list":
        _list_sessions(cli_state, limit=10)

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
        render_error(
            console,
            f"Unknown subcommand: /sessions {subcommand}. Available: list, delete",
            error_type="error",
        )


# ━━━━━━━━━━ Helper Functions ━━━━━━━━━━
def _display_session_info(cli_state) -> None:
    """Display current session metadata."""
    console = cli_state.console

    try:
        session_data = cli_state.memory_manager.get_session(cli_state.session_id)

        if not session_data:
            render_error(
                console,
                f"Session not found: {cli_state.session_id}",
                error_type="error",
            )
            return

        # Count messages
        message_count = cli_state.memory_manager.count_messages(cli_state.session_id)

        # Prepare display data
        display_data = {
            "session_id": cli_state.session_id,
            "created_at": session_data.get("created_at", "N/A"),
            "aig_filename": session_data.get("aig_filename") or "(none)",
            "model_choice": session_data.get("model_choice", "unknown"),
            "messages": message_count,
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
        conn = cli_state.memory_manager._get_conn()

        # Query recent sessions
        rows = conn.execute(
            """SELECT session_id, created_at, aig_filename, model_choice
               FROM sessions
               ORDER BY created_at DESC
               LIMIT ?""",
            (limit,),
        ).fetchall()

        if not rows:
            console.print("[dim]No sessions found[/dim]")
            return

        console.print()
        console.print(f"[bold cyan]Recent Sessions (latest {len(rows)})[/bold cyan]")
        render_divider(console)

        for i, row in enumerate(rows, 1):
            session_id = row["session_id"]
            created_at = row["created_at"]
            aig_filename = row["aig_filename"] or "(none)"
            model_choice = row["model_choice"]

            # Highlight current session
            if session_id == cli_state.session_id:
                prefix = "[bold green]→[/bold green]"
            else:
                prefix = " "

            console.print(
                f"{prefix} [{i}] {session_id[:8]} | "
                f"[cyan]{created_at[:10]}[/cyan] | "
                f"[yellow]{aig_filename}[/yellow] | "
                f"[magenta]{model_choice}[/magenta]"
            )

        console.print()

    except Exception as e:
        render_error(
            console,
            f"Failed to list sessions: {e}",
            error_type="error",
        )


def _export_session(cli_state) -> None:
    """Export current session to JSON file."""
    console = cli_state.console

    try:
        import json
        from pathlib import Path

        # Get all messages
        messages = cli_state.memory_manager.get_all_messages(cli_state.session_id)

        # Get session metadata
        session_data = cli_state.memory_manager.get_session(cli_state.session_id)

        # Prepare export data
        export_data = {
            "session_id": cli_state.session_id,
            "created_at": session_data.get("created_at"),
            "aig_filename": session_data.get("aig_filename"),
            "model_choice": session_data.get("model_choice"),
            "messages": messages,
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
    """Delete a session."""
    console = cli_state.console

    session_id = session_id.strip()

    # Prevent deleting current session
    if session_id == cli_state.session_id or session_id == cli_state.session_id[:8]:
        render_error(
            console,
            "Cannot delete current session",
            error_type="error",
        )
        return

    try:
        cli_state.memory_manager.delete_session(session_id)
        render_success(
            console,
            f"Session deleted: {session_id}",
            title="Deletion Complete",
        )

    except Exception as e:
        render_error(
            console,
            f"Failed to delete session: {e}",
            error_type="error",
        )
