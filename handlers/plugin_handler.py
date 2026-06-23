"""
Plugin Handler - /plugin command

Manages CktClaw plugins: list, install, remove.
"""

from rich.console import Console
from rich.table import Table
from rich.panel import Panel


def handle_plugin_command(args: str, cli_state) -> None:
    """
    Handle /plugin subcommands.

    Usage:
        /plugin              — list installed plugins
        /plugin list         — list installed plugins
        /plugin install <path-or-url>  — install a plugin
        /plugin remove <name>          — remove a plugin
        /plugin tools        — list tools contributed by plugins

    Args:
        args: Subcommand and arguments
        cli_state: Global CLI state
    """
    console = cli_state.console

    parts = args.strip().split(maxsplit=1)
    subcmd = parts[0].lower() if parts else "list"
    subargs = parts[1].strip() if len(parts) > 1 else ""

    if subcmd in ("list", "ls", ""):
        _plugin_list(console)
    elif subcmd == "install":
        _plugin_install(console, subargs)
    elif subcmd in ("remove", "uninstall", "rm"):
        _plugin_remove(console, subargs)
    elif subcmd == "tools":
        _plugin_tools(console)
    else:
        console.print(
            "[yellow]Usage: /plugin [list|install <path-or-url>|remove <name>|tools][/yellow]"
        )


def _plugin_list(console: Console) -> None:
    """List all installed plugins."""
    from ..plugins import get_plugin_manager

    mgr = get_plugin_manager()
    plugins = mgr.loaded_plugins

    if not plugins:
        console.print("[dim]No plugins installed.[/dim]")
        console.print("[dim]Install with: /plugin install <path-or-git-url>[/dim]")
        return

    table = Table(title="Installed Plugins", border_style="cyan")
    table.add_column("Name", style="bold cyan")
    table.add_column("Version", style="green")
    table.add_column("Status", style="yellow")
    table.add_column("Tools", style="dim")
    table.add_column("Skills", style="dim")

    for name, info in plugins.items():
        from ..plugins.base import PluginType
        tools = info.contributions.get(PluginType.TOOL, [])
        skills = info.contributions.get(PluginType.SKILL, [])
        table.add_row(
            name,
            info.version,
            info.status.value,
            ", ".join(tools) if tools else "-",
            ", ".join(skills) if skills else "-",
        )

    console.print(table)


def _plugin_install(console: Console, source: str) -> None:
    """Install a plugin from path or git URL."""
    if not source:
        console.print("[yellow]Usage: /plugin install <local-path-or-git-url>[/yellow]")
        return

    from ..plugins import get_plugin_manager

    mgr = get_plugin_manager()

    console.print(f"[dim]Installing plugin from: {source}[/dim]")

    if source.startswith("http://") or source.startswith("https://") or source.startswith("git@"):
        info = mgr.install_from_git(source)
    else:
        info = mgr.install_from_path(source)

    if info:
        console.print(
            f"[green]Installed plugin: {info.name} v{info.version} "
            f"({info.status.value})[/green]"
        )
        if info.contributions:
            from ..plugins.base import PluginType
            for ptype, items in info.contributions.items():
                console.print(f"  [dim]{ptype.value}s: {', '.join(items)}[/dim]")
        if info.skill_names:
            names = info.skill_names[:8]
            extra = len(info.skill_names) - 8
            suffix = f" ... (+{extra} more)" if extra > 0 else ""
            console.print(f"  [dim]skills registered: {', '.join(names)}{suffix}[/dim]")

        # Register plugin tools in the ToolRegistry
        _register_plugin_tools(info.name)
    else:
        console.print("[red]Failed to install plugin. Check logs for details.[/red]")


def _plugin_remove(console: Console, name: str) -> None:
    """Remove an installed plugin."""
    if not name:
        console.print("[yellow]Usage: /plugin remove <plugin-name>[/yellow]")
        return

    from ..plugins import get_plugin_manager

    mgr = get_plugin_manager()

    if mgr.uninstall(name):
        # Also unregister tools from ToolRegistry
        from ..tools import get_tool_registry
        registry = get_tool_registry()
        removed = registry.unregister_by_source(f"plugin:{name}")
        console.print(f"[green]Removed plugin: {name} ({removed} tools unregistered)[/green]")
    else:
        console.print(f"[red]Plugin not found: {name}[/red]")


def _plugin_tools(console: Console) -> None:
    """List tools contributed by plugins."""
    from ..plugins import get_plugin_manager

    mgr = get_plugin_manager()
    tools = mgr.list_tools()

    if not tools:
        console.print("[dim]No plugin tools registered.[/dim]")
        return

    table = Table(title="Plugin Tools", border_style="cyan")
    table.add_column("Tool", style="bold cyan")
    table.add_column("Plugin", style="green")

    for tool_name, plugin_name in tools.items():
        table.add_row(tool_name, plugin_name)

    console.print(table)


def _register_plugin_tools(plugin_name: str) -> None:
    """Register a plugin's tools into the ToolRegistry."""
    from ..plugins import get_plugin_manager
    from ..tools import get_tool_registry

    mgr = get_plugin_manager()
    manifest = mgr.get_manifest(plugin_name)
    if not manifest:
        return

    registry = get_tool_registry()
    info = mgr.get_plugin(plugin_name)
    if not info:
        return

    # Try to import and instantiate each tool
    for tool_entry in manifest.tools:
        try:
            handler_spec = tool_entry.handler
            if ":" in handler_spec:
                module_path, class_name = handler_spec.rsplit(":", 1)
            else:
                continue

            import importlib
            import importlib.util
            import sys

            # Try to import from plugin directory
            plugin_str = str(info.path)
            if plugin_str not in sys.path:
                sys.path.insert(0, plugin_str)

            module_file = info.path / module_path.replace(".", "/")
            if module_file.with_suffix(".py").is_file():
                spec = importlib.util.spec_from_file_location(
                    f"cktclaw_plugin_{module_path}",
                    module_file.with_suffix(".py"),
                )
                if spec and spec.loader:
                    module = importlib.util.module_from_spec(spec)
                    spec.loader.exec_module(module)
                    tool_class = getattr(module, class_name, None)
                    if tool_class:
                        tool_instance = tool_class()
                        registry.register(
                            tool_instance,
                            source=f"plugin:{plugin_name}",
                        )
        except Exception:
            pass
