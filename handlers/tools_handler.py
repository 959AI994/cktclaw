"""
Tools Handler - /tools command

Lists all registered tools in the CktClaw ToolRegistry.
"""

from rich.table import Table


def handle_tools_command(args: str, cli_state) -> None:
    """
    Handle /tools command — list registered tools.

    Usage:
        /tools             — list all tools
        /tools eda         — list EDA tools only
        /tools system      — list system tools only
        /tools <name>      — show details for a specific tool

    Args:
        args: Subcommand/filter
        cli_state: Global CLI state
    """
    console = cli_state.console

    from ..tools import get_tool_registry
    registry = get_tool_registry()

    filter_arg = args.strip().lower() if args else ""

    if filter_arg and filter_arg not in ("eda", "system", "agent", "plugin", "all"):
        # Show details for a specific tool
        _show_tool_detail(console, registry, filter_arg)
        return

    tools = registry.list_tools()

    if not tools:
        console.print("[dim]No tools registered. The ToolRegistry is empty.[/dim]")
        return

    # Filter by category
    if filter_arg and filter_arg != "all":
        tools = [t for t in tools if t.category == filter_arg]
        if not tools:
            console.print(f"[dim]No tools in category '{filter_arg}'.[/dim]")
            return

    table = Table(title="Registered Tools", border_style="cyan")
    table.add_column("Name", style="bold cyan", no_wrap=True)
    table.add_column("Category", style="green")
    table.add_column("R/O", style="yellow", justify="center")
    table.add_column("Source", style="dim")
    table.add_column("Description", style="white", max_width=50)

    for tool in sorted(tools, key=lambda t: (t.category, t.name)):
        source = registry.get_source(tool.name) or "unknown"
        ro = "R" if tool.read_only else "W"
        desc = tool.description[:50] + "..." if len(tool.description) > 50 else tool.description
        table.add_row(tool.name, tool.category, ro, source, desc)

    console.print(table)
    console.print(f"[dim]Total: {len(tools)} tools. Use /tools <name> for details.[/dim]")


def _show_tool_detail(console, registry, name: str) -> None:
    """Show detailed info for a specific tool."""
    tool = registry.get(name)
    if not tool:
        console.print(f"[red]Tool not found: {name}[/red]")
        console.print(f"[dim]Available: {', '.join(registry.list_names())}[/dim]")
        return

    from rich.panel import Panel
    import json

    params_str = json.dumps(tool.parameters, indent=2, ensure_ascii=False) if tool.parameters else "{}"

    detail = (
        f"[bold cyan]{tool.name}[/bold cyan]\n"
        f"\n"
        f"[bold]Description:[/bold] {tool.description}\n"
        f"[bold]Category:[/bold] {tool.category}\n"
        f"[bold]Read-only:[/bold] {tool.read_only}\n"
        f"[bold]Source:[/bold] {registry.get_source(tool.name) or 'unknown'}\n"
    )
    if tool.requires:
        detail += f"[bold]Requires:[/bold] {', '.join(tool.requires)}\n"

    detail += f"\n[bold]Parameters (JSON Schema):[/bold]\n[dim]{params_str}[/dim]"

    console.print(Panel(detail, title=f"Tool: {tool.name}", border_style="cyan"))
