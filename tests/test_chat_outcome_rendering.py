"""Regression tests for chat completion status and compact tool rendering."""

from rich.console import Console


def test_completion_summary_can_render_incomplete():
    from cktclaw.ui.renderer import render_completion_summary

    console = Console(record=True, force_terminal=False, width=100)
    render_completion_summary(
        console,
        {"total": 1.25},
        title="Incomplete with deepseek",
        status="incomplete",
        detail="Query loop reached max turns.",
    )
    text = console.export_text()
    assert "Operation incomplete" in text
    assert "Operation completed" not in text


def test_tool_call_compact_renderer_groups_bash_calls():
    from cktclaw.handlers.chat_handler_v3 import ToolCallCompactRenderer

    class TC:
        def __init__(self, idx: str) -> None:
            self.id = idx
            self.name = "bash"

    console = Console(record=True, force_terminal=False, width=120)
    ToolCallCompactRenderer(console).render(
        [TC("1"), TC("2"), TC("3")],
        [
            ("1", "ok", "[green]OK[/green]"),
            ("2", "Error: compile failed", "[red]FAIL[/red]"),
            ("3", "Error: sim failed", "[red]FAIL[/red]"),
        ],
    )
    text = console.export_text()
    assert "Tool calls" in text
    assert "bash" in text
    assert "2" in text
    assert text.count("bash") <= 2
