"""
Rich Rendering Components

Provides reusable Rich components for consistent CLI output including:
- Spinners and progress bars for long operations
- Syntax highlighting for Verilog code
- Markdown rendering for analysis reports
- Tables for metrics and data display
- Panels for status messages and summaries
"""

import time
from typing import Optional, List, Dict, Any, Callable
from rich.console import Console
from rich.status import Status
from rich.progress import Progress, BarColumn, TextColumn, TimeRemainingColumn
from rich.syntax import Syntax
from rich.markdown import Markdown
from rich.table import Table
from rich.panel import Panel
from rich.text import Text
from rich.box import ROUNDED
from rich.rule import Rule
from contextlib import contextmanager

from .colors import Icons, Colors, Styles, OPERATION_COLORS, STYLE_MAP


# ━━━━━━━━━━ Helper: Create Rich Console ━━━━━━━━━━
def create_console() -> Console:
    """Create and return a Rich console instance"""
    return Console(force_terminal=None, legacy_windows=False, soft_wrap=False)


# ━━━━━━━━━━ Status/Progress for Long Operations ━━━━━━━━━━
@contextmanager
def render_spinner(console: Console, text: str, style: str = "cyan"):
    """
    Context manager for short operations (< 10 seconds).
    Shows animated spinner with message.

    Usage:
        with render_spinner(console, "Processing..."):
            result = await operation()
    """
    with console.status(f"[{style}]{text}", spinner="dots") as status:
        yield status


@contextmanager
def render_progress(
    console: Console,
    steps: List[str],
    title: str = "Processing",
) -> Progress:
    """
    Context manager for longer operations (> 10 seconds).
    Shows multi-step progress bar with milestones.

    Usage:
        with render_progress(console, ["Step1", "Step2", "Step3"]) as progress:
            task = progress.add_task(title, total=len(steps))
            await step1(); progress.update(task, advance=1)
            await step2(); progress.update(task, advance=1)
    """
    with Progress(
        TextColumn("[progress.description]{task.description}"),
        BarColumn(bar_width=30),
        TextColumn("[progress.percentage]{task.percentage:>3.0f}%"),
        TimeRemainingColumn(),
        console=console,
    ) as progress:
        yield progress


# ━━━━━━━━━━ Code Display ━━━━━━━━━━
def render_verilog_code(
    console: Console,
    code: str,
    theme: str = "monokai",
    max_lines: Optional[int] = None,
) -> None:
    """
    Render Verilog code with syntax highlighting and line numbers.

    Args:
        console: Rich console instance
        code: Verilog source code
        theme: Syntax theme (monokai, dracula, etc)
        max_lines: Limit output to first N lines (None = all)
    """
    lines = code.split("\n")
    if max_lines and len(lines) > max_lines:
        displayed_code = "\n".join(lines[:max_lines])
        remaining = len(lines) - max_lines
        footer = f"\n... ({remaining} more lines)"
    else:
        displayed_code = code
        footer = ""

    syntax = Syntax(
        displayed_code,
        "verilog",
        theme=theme,
        line_numbers=True,
        line_range=None,
        highlight_lines=set(),
        word_wrap=True,
    )
    console.print(syntax)

    if footer:
        console.print(f"[dim]{footer}[/dim]")


# ━━━━━━━━━━ Report/Analysis Display ━━━━━━━━━━
def render_analysis_report(console: Console, markdown_text: str, title: str = "Circuit Analysis") -> None:
    """
    Render analysis report as Rich Markdown in a bordered panel.

    Args:
        console: Rich console instance
        markdown_text: Markdown-formatted analysis text
        title: Panel title
    """
    markdown = Markdown(markdown_text)

    # Render with bordered panel for better visual separation
    panel = Panel(
        markdown,
        title=f"[bold cyan]{title}[/bold cyan]",
        border_style="cyan",
        box=ROUNDED,
        padding=(1, 2),
    )
    console.print(panel)


# ━━━━━━━━━━ Metrics Table ━━━━━━━━━━
def render_metrics_table(
    console: Console,
    metrics: Dict[str, Any],
    title: str = "Circuit Metrics",
) -> None:
    """
    Render circuit metrics as a Rich table.

    Args:
        console: Rich console instance
        metrics: Dictionary of {metric_name: value}
        title: Table title
    """
    table = Table(title=title, show_header=True, header_style="bold cyan")
    table.add_column("Metric", style="cyan")
    table.add_column("Value", style="bold green")

    for key, value in metrics.items():
        # Format key: snake_case → Title Case
        formatted_key = key.replace("_", " ").title()
        table.add_row(formatted_key, str(value))

    console.print(table)


# ━━━━━━━━━━ Summary Panel ━━━━━━━━━━
def render_completion_summary(
    console: Console,
    timing_dict: Dict[str, float],
    title: str = "Completion Summary",
    status: str = "completed",
    detail: str = "",
) -> None:
    """
    Render completion summary with timing information.

    Args:
        console: Rich console instance
        timing_dict: Dictionary of {operation: elapsed_seconds}
        title: Panel title
    """
    status_norm = (status or "completed").lower()
    if status_norm == "failed":
        icon = Icons.ERROR
        style = "red"
        label = "Operation failed"
    elif status_norm == "incomplete":
        icon = Icons.WARNING
        style = "yellow"
        label = "Operation incomplete"
    else:
        icon = Icons.SUCCESS
        style = "green"
        label = "Operation completed"

    lines = [f"[bold {style}]{icon} {label}[/bold {style}]\n"]
    if detail:
        lines.append(f"{detail}\n")

    if timing_dict:
        lines.append("[bold]Timing breakdown:[/bold]")
        total_time = 0
        for op_name, elapsed in timing_dict.items():
            formatted_op = op_name.replace("_", " ").title()
            lines.append(f"  • {formatted_op}: {elapsed:.2f}s")
            total_time += elapsed
        lines.append(f"\n[bold]Total time:[/bold] {total_time:.2f}s")

    panel = Panel(
        "\n".join(lines),
        title=title,
        border_style=style,
        box=ROUNDED,
        padding=(1, 2),
    )
    console.print(panel)


# ━━━━━━━━━━ Error Display ━━━━━━━━━━
def render_error(
    console: Console,
    error_msg: str,
    error_type: str = "error",
    title: str = "CktClaw Error",
) -> None:
    """
    Render error message in a styled panel.

    Args:
        console: Rich console instance
        error_msg: Error message text
        error_type: Type of error (error, file_error, gpu_error, internal)
        title: Panel title
    """
    icons_map = {
        "error": Icons.ERROR,
        "file_error": Icons.ERROR,
        "gpu_error": Icons.WARNING,
        "internal": Icons.ERROR,
    }
    icon = icons_map.get(error_type, Icons.ERROR)

    panel = Panel(
        f"[bold red]{icon} {error_msg}[/bold red]",
        title=f"[bold]{title}[/bold]",
        border_style="red",
        box=ROUNDED,
        padding=(1, 2),
    )
    console.print(panel)


# ━━━━━━━━━━ Success Display ━━━━━━━━━━
def render_success(console: Console, message: str, title: str = "Success") -> None:
    """
    Render success message in a styled panel.

    Args:
        console: Rich console instance
        message: Success message text
        title: Panel title
    """
    panel = Panel(
        f"[bold green]{Icons.SUCCESS} {message}[/bold green]",
        title=f"[bold]{title}[/bold]",
        border_style="green",
        box=ROUNDED,
        padding=(1, 2),
    )
    console.print(panel)


# ━━━━━━━━━━ Session Info Display ━━━━━━━━━━
def render_session_info(
    console: Console,
    session_data: Dict[str, Any],
) -> None:
    """
    Render current session information as a table.

    Args:
        console: Rich console instance
        session_data: Session metadata dictionary
    """
    table = Table(title="Session Information", show_header=False)
    table.add_column("Key", style="cyan")
    table.add_column("Value", style="bold green")

    for key, value in session_data.items():
        formatted_key = key.replace("_", " ").title()
        table.add_row(formatted_key, str(value))

    console.print(table)


# ━━━━━━━━━━ Header & Footer ━━━━━━━━━━
def render_header(
    console: Console,
    title: str,
    subtitle: Optional[str] = None,
) -> None:
    """
    Render a formatted header with optional subtitle.

    Args:
        console: Rich console instance
        title: Header title
        subtitle: Optional subtitle
    """
    console.print(f"\n[bold cyan]{'═'*60}[/bold cyan]")
    console.print(f"[bold cyan]{title:^60}[/bold cyan]")
    if subtitle:
        console.print(f"[dim]{subtitle:^60}[/dim]")
    console.print(f"[bold cyan]{'═'*60}[/bold cyan]\n")


def render_divider(console: Console, char: str = "━", width: int = 70) -> None:
    """
    Render a simple divider line.

    Args:
        console: Rich console instance
        char: Character to use for divider
        width: Width of divider
    """
    console.print(f"[dim]{char * width}[/dim]")


# ━━━━━━━━━━ AIG Processing Pipeline (with auto-switching) ━━━━━━━━━━
@contextmanager
def render_aig_processing(
    console: Console,
    operation_name: str,
    estimated_duration: float = None,
):
    """
    Auto-switching context manager for AIG processing operations.
    Uses spinner for short operations (< 10s), progress for longer.

    Args:
        console: Rich console instance
        operation_name: Name of operation (e.g., "Converting AIG to Verilog")
        estimated_duration: Estimated duration in seconds (if None, use spinner)

    Usage:
        with render_aig_processing(console, "Converting AIG to Verilog", estimated_duration=15):
            result = await operation()
    """
    if estimated_duration is None or estimated_duration < 10:
        # Use spinner for quick operations
        with render_spinner(console, operation_name, style="cyan") as status:
            yield status
    else:
        # Use progress bar for longer operations
        with render_progress(console, ["Processing"], title=operation_name) as progress:
            yield progress


# ━━━━━━━━━━ Prompt/Input Display ━━━━━━━━━━
def render_prompt(
    console: Console,
    session_id: str,
    engine: str,
    memory_rounds: int,
) -> str:
    """
    Render CLI prompt with session and engine info.

    Args:
        console: Rich console instance
        session_id: Current session ID
        engine: Current engine (deepseek/local)
        memory_rounds: Current number of memory rounds

    Returns:
        Formatted prompt string
    """
    # Build prompt with session info
    session_short = session_id[:8]
    engine_color = "cyan" if engine == "deepseek" else "magenta"

    prompt_text = (
        f"[bold green]logicrt[/bold green]"
        f" [{session_short}]"
        f" [{engine_color}]{engine}[/{engine_color}]"
        f" [{memory_rounds}🧠]"
        f" > "
    )
    return prompt_text


# ━━━━━━━━━━ Turn Separator ━━━━━━━━━━
def render_turn_separator(console: Console) -> None:
    """
    Render a full-width horizontal rule to separate conversation turns.
    Provides clear visual boundary between history and the new input area.

    Args:
        console: Rich console instance
    """
    console.print(Rule(style="dim gray"))


# ━━━━━━━━━━ Chat Bubble Rendering ━━━━━━━━━━
def render_user_message(console: Console, message: str) -> None:
    """
    Render user's chat message as a blue-bordered panel (chat bubble).

    Args:
        console: Rich console instance
        message: User's raw text input
    """
    panel = Panel(
        Text(message),
        title="[bold blue]🧑 You[/bold blue]",
        title_align="left",
        border_style="blue",
        box=ROUNDED,
        padding=(0, 1),
        expand=False,
    )
    console.print(panel)


def render_assistant_message(console: Console, markdown_text: str) -> None:
    """
    Render assistant/model response as a magenta-bordered panel (chat bubble).
    Content is rendered as Rich Markdown for proper formatting.

    Args:
        console: Rich console instance
        markdown_text: Markdown-formatted response from LLM
    """
    markdown = Markdown(markdown_text)

    panel = Panel(
        markdown,
        title="[bold magenta]🤖 CktClaw Agent[/bold magenta]",
        title_align="left",
        border_style="magenta",
        box=ROUNDED,
        padding=(0, 1),
        expand=False,
    )
    console.print(panel)


# ━━━━━━━━━━ Formatting Utilities ━━━━━━━━━━
def format_time(seconds: float) -> str:
    """Format seconds as human-readable time"""
    if seconds < 1:
        return f"{seconds*1000:.0f}ms"
    elif seconds < 60:
        return f"{seconds:.1f}s"
    else:
        return f"{seconds/60:.1f}m"


def format_size(bytes_count: int) -> str:
    """Format bytes as human-readable size"""
    for unit in ["B", "KB", "MB", "GB"]:
        if bytes_count < 1024:
            return f"{bytes_count:.1f}{unit}"
        bytes_count /= 1024
    return f"{bytes_count:.1f}TB"
