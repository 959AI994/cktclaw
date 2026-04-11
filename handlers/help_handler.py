"""
Help Handler - /help command

Displays comprehensive command documentation and usage tips.
"""

from ..config import HELP_TEXT, ABOUT_TEXT
from ..ui import render_header


def show_help(cli_state) -> None:
    """
    Display help text with all available commands.

    Command: /help or /?

    Args:
        cli_state: Global CLI state (CLIState instance)
    """
    console = cli_state.console

    console.print()
    console.print(HELP_TEXT)
    console.print()


def show_about(cli_state) -> None:
    """
    Display CktClaw platform introduction and key capabilities.
    Command: /about
    """
    console = cli_state.console
    console.print()
    console.print(ABOUT_TEXT)
    console.print()
