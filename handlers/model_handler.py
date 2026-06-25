"""
Model Handler - /model command

Interactive provider + model selection with arrow-key navigation.

Lists every known LLM provider (DeepSeek / Claude / OpenAI / local-compatible),
shows whether each is ready or needs an API key, and lets the user:
  • switch to any configured provider,
  • configure an API key (or local base_url) on the spot — persisted to
    ~/.cktclaw/config.yaml so it survives restarts,
  • pick a specific model for the chosen provider.

  ❯  🐋 DeepSeek      ✅ 已就绪 ◀ 当前
     🦋 Claude        ⛔ 未配置（回车配置）

  ↑↓ 选择 · Enter 确认 · Esc 取消
"""

import getpass
import os
import select as _select
import sys
import termios
import tty
from typing import Callable, List, Optional

from rich.box import ROUNDED
from rich.live import Live
from rich.panel import Panel

from ..ui import render_success

try:
    from ..llm.router import get_model_router
except Exception:  # pragma: no cover - llm stack optional at import time
    get_model_router = None  # type: ignore


# Maps the legacy cli_state.current_engine string to a ModelRouter provider.
# Local engines (logicrt, qwen) have no ModelRouter provider and are left unmapped.
_ENGINE_TO_PROVIDER = {
    "deepseek": "deepseek",
    "claude": "claude",
    "openai": "openai",
    "local": "local",
    "logicrt": None,
    "qwen": None,
}


# ━━━━━━━━━━ Provider catalog ━━━━━━━━━━
# Static metadata for every selectable provider. `models` is a starter list of
# common choices; the user can also type a custom model name.
PROVIDER_CATALOG = [
    {
        "key": "deepseek",
        "label": "DeepSeek",
        "icon": "🐋",
        "desc": "云端 · 性价比高，中文友好",
        "needs": "key",
        "default_base_url": "https://api.deepseek.com",
        "default_model": "deepseek-chat",
        "models": ["deepseek-chat", "deepseek-reasoner"],
    },
    {
        "key": "claude",
        "label": "Anthropic Claude",
        "icon": "🦋",
        "desc": "云端 · 强代码 / 推理（需 anthropic 包）",
        "needs": "key",
        "default_base_url": None,
        "default_model": "claude-sonnet-4-6",
        "models": [
            "claude-sonnet-4-6",
            "claude-opus-4-8",
            "claude-haiku-4-5-20251001",
        ],
    },
    {
        "key": "openai",
        "label": "OpenAI",
        "icon": "🟢",
        "desc": "云端 · GPT 系列",
        "needs": "key",
        "default_base_url": "https://api.openai.com/v1",
        "default_model": "gpt-4o",
        "models": ["gpt-4o", "gpt-4o-mini", "o3-mini"],
    },
    {
        "key": "local",
        "label": "本地 / 自定义",
        "icon": "💻",
        "desc": "OpenAI 兼容：vLLM / Ollama / LM Studio",
        "needs": "base_url",
        "default_base_url": "http://localhost:11434/v1",
        "default_model": "default",
        "models": [],
    },
]


def _catalog_entry(provider_key: str) -> Optional[dict]:
    for entry in PROVIDER_CATALOG:
        if entry["key"] == provider_key:
            return entry
    return None


def _sync_router_after_switch(selected_engine: str) -> None:
    """Sync ModelRouter active provider to match a legacy engine selection (best-effort)."""
    provider_name = _ENGINE_TO_PROVIDER.get(selected_engine)
    if not provider_name:
        return
    try:
        router = get_model_router()
        switched = router.switch(provider_name)
        if not switched:
            import logging as _log
            _log.getLogger(__name__).warning(
                f"ModelRouter.switch('{provider_name}') failed — "
                "provider may not be configured"
            )
    except Exception as _e:
        import logging as _log
        _log.getLogger(__name__).warning(f"ModelRouter sync failed: {_e}")


# ━━━━━━━━━━ Status detection ━━━━━━━━━━
def _provider_status(provider_key: str) -> tuple:
    """
    Determine a provider's readiness.

    Returns (status, note) where status is one of:
      "ready"     — configured and usable now,
      "configured_unusable" — has a key but cannot run (e.g. Claude Code token,
                    or anthropic package missing),
      "missing"   — not configured.
    """
    try:
        from ..api_credentials import (
            get_anthropic_api_key,
            get_deepseek_api_key,
            get_openai_api_key,
        )
    except Exception:
        return ("missing", "")

    # Source of truth for "ready" is the live router.
    ready_set = set()
    try:
        if get_model_router is not None:
            ready_set = set(get_model_router().available_providers)
    except Exception:
        ready_set = set()

    if provider_key == "deepseek":
        key = get_deepseek_api_key(required=False)
        if provider_key in ready_set:
            return ("ready", "")
        return ("missing", "") if not key else ("configured_unusable", "key 已配置")

    if provider_key == "claude":
        key = get_anthropic_api_key(required=False)
        if not key:
            return ("missing", "")
        if key.startswith("sk-ant-oat"):
            return ("configured_unusable", "Claude Code token 不可直连")
        if provider_key in ready_set:
            return ("ready", "")
        return ("configured_unusable", "需 pip install anthropic")

    if provider_key == "openai":
        key = get_openai_api_key(required=False)
        if provider_key in ready_set:
            return ("ready", "")
        return ("missing", "") if not key else ("configured_unusable", "key 已配置")

    if provider_key == "local":
        if provider_key in ready_set:
            return ("ready", "")
        return ("missing", "")

    return ("missing", "")


_STATUS_TAG = {
    "ready": "[green]✅ 已就绪[/green]",
    "configured_unusable": "[yellow]⚠️ 不可用[/yellow]",
    "missing": "[dim]⛔ 未配置[/dim]",
}


# ━━━━━━━━━━ Low-level Key Reader ━━━━━━━━━━
def _read_key():
    """
    Read a single keypress from stdin in raw mode.

    Returns one of: 'up', 'down', 'enter', 'esc', 'ctrl_c', or None.
    """
    fd = sys.stdin.fileno()
    old_settings = termios.tcgetattr(fd)
    try:
        tty.setraw(fd)
        ch = os.read(fd, 1)

        if ch == b'\x1b':
            if _select.select([fd], [], [], 0.05)[0]:
                ch2 = os.read(fd, 1)
                if ch2 == b'[' and _select.select([fd], [], [], 0.05)[0]:
                    ch3 = os.read(fd, 1)
                    if ch3 == b'A':
                        return 'up'
                    if ch3 == b'B':
                        return 'down'
            return 'esc'

        if ch in (b'\r', b'\n'):
            return 'enter'
        if ch == b'\x03':          # Ctrl-C
            return 'ctrl_c'

        return None
    finally:
        termios.tcsetattr(fd, termios.TCSADRAIN, old_settings)


# ━━━━━━━━━━ Generic arrow-key menu ━━━━━━━━━━
def _arrow_menu(
    console,
    title: str,
    subtitle: str,
    rows: List,
    render_row: Callable[[object, bool], str],
    start_idx: int = 0,
) -> Optional[int]:
    """Show a transient arrow-key menu. Returns selected index, or None if cancelled."""
    if not rows:
        return None
    selected = max(0, min(start_idx, len(rows) - 1))

    def _build():
        lines = [render_row(row, i == selected) for i, row in enumerate(rows)]
        return Panel(
            "\n".join(lines),
            title=title,
            subtitle=subtitle,
            subtitle_align="center",
            border_style="cyan",
            box=ROUNDED,
            padding=(1, 2),
            expand=False,
        )

    console.print()
    try:
        with Live(_build(), console=console, auto_refresh=False, transient=True) as live:
            while True:
                key = _read_key()
                if key == 'up':
                    selected = (selected - 1) % len(rows)
                    live.update(_build(), refresh=True)
                elif key == 'down':
                    selected = (selected + 1) % len(rows)
                    live.update(_build(), refresh=True)
                elif key == 'enter':
                    return selected
                elif key in ('esc', 'ctrl_c'):
                    return None
    except Exception:
        return None


# ━━━━━━━━━━ Public API ━━━━━━━━━━
def select_model_interactive(cli_state) -> None:
    """
    Interactive provider + model selection.

    ↑/↓ moves the highlight, Enter confirms, Esc cancels. Choosing an
    unconfigured provider walks the user through entering an API key, which is
    saved to ~/.cktclaw/config.yaml.
    """
    console = cli_state.console
    current_engine = getattr(cli_state, "current_engine", "deepseek")

    # ── Build provider rows with live status ──
    rows = []  # list of (entry, status, note)
    for entry in PROVIDER_CATALOG:
        status, note = _provider_status(entry["key"])
        rows.append((entry, status, note))

    start_idx = 0
    for i, (entry, _s, _n) in enumerate(rows):
        if entry["key"] == current_engine:
            start_idx = i

    def _render_provider(row, is_selected: bool) -> str:
        entry, status, note = row
        tag = _STATUS_TAG.get(status, "")
        cur = " [bold green]◀ 当前[/bold green]" if entry["key"] == current_engine else ""
        note_str = f"  [dim]({note})[/dim]" if note else ""
        label = f"{entry['icon']}  {entry['label']}"
        if is_selected:
            return (
                f"  [bold cyan]❯[/bold cyan] [bold reverse] {label} [/bold reverse]"
                f"  {tag}{note_str}{cur}\n"
                f"      [dim]{entry['desc']}[/dim]"
            )
        return f"     [bold]{label}[/bold]  {tag}{note_str}{cur}"

    idx = _arrow_menu(
        console,
        title="[bold cyan]🔧 选择模型提供方 Provider[/bold cyan]",
        subtitle="[dim]↑↓ 选择 · Enter 确认 · Esc 取消[/dim]",
        rows=rows,
        render_row=_render_provider,
        start_idx=start_idx,
    )
    if idx is None:
        console.print("[yellow]已取消 Cancelled[/yellow]\n")
        return

    entry, status, _note = rows[idx]
    provider_key = entry["key"]

    # ── Ensure the provider is configured ──
    if status != "ready":
        if not _configure_provider(console, entry):
            return  # user cancelled or configuration failed

    # ── Optional: choose a model ──
    _choose_model(console, entry)

    # ── Activate the provider ──
    if not _activate_provider(console, cli_state, provider_key):
        return

    # ── Success feedback ──
    model = ""
    try:
        model = get_model_router().get_model(provider_key) or ""
    except Exception:
        pass
    console.print()
    render_success(
        console,
        f"已切换到 {entry['icon']} {entry['label']}"
        + (f"  ·  模型 {model}" if model else ""),
        title="模型切换成功",
    )
    console.print()


# ━━━━━━━━━━ Configuration (API key / base_url) ━━━━━━━━━━
def _configure_provider(console, entry: dict) -> bool:
    """Prompt for and persist the credential a provider needs. Returns True on success."""
    provider_key = entry["key"]

    if entry["needs"] == "key":
        console.print(
            f"\n[cyan]配置 {entry['icon']} {entry['label']} API Key[/cyan] "
            f"[dim](直接回车取消)[/dim]"
        )
        try:
            key = getpass.getpass("  API Key: ").strip()
        except (EOFError, KeyboardInterrupt):
            key = ""
        if not key:
            console.print("[yellow]已取消 Cancelled[/yellow]\n")
            return False

        if provider_key == "claude" and key.startswith("sk-ant-oat"):
            console.print(
                "[red]这是 Claude Code 订阅版 OAuth token（sk-ant-oat…），无法直连 API。"
                "请使用标准 API key（sk-ant-api…）。[/red]\n"
            )
            return False
        if provider_key == "claude":
            try:
                import anthropic  # noqa: F401
            except ImportError:
                console.print(
                    "[yellow]提示：未安装 anthropic 包，正在尝试保存 key，但需要先 "
                    "`pip install anthropic` 才能使用 Claude。[/yellow]"
                )

        updates = {"llm": {provider_key: {"api_key": key}}}
        if entry.get("default_base_url"):
            updates["llm"][provider_key]["base_url"] = entry["default_base_url"]
        updates["llm"][provider_key]["model"] = entry["default_model"]
        _save_and_reload(console, updates)
        return True

    if entry["needs"] == "base_url":
        console.print(
            f"\n[cyan]配置 {entry['icon']} {entry['label']}[/cyan] "
            f"[dim](直接回车取消)[/dim]"
        )
        try:
            base_url = input(
                f"  Base URL [{entry['default_base_url']}]: "
            ).strip() or entry["default_base_url"]
            model = input(f"  Model [{entry['default_model']}]: ").strip() or entry["default_model"]
            api_key = getpass.getpass("  API Key (无则回车): ").strip() or "none"
        except (EOFError, KeyboardInterrupt):
            console.print("[yellow]已取消 Cancelled[/yellow]\n")
            return False
        if not base_url:
            console.print("[yellow]已取消 Cancelled[/yellow]\n")
            return False

        updates = {"llm": {provider_key: {"base_url": base_url, "model": model, "api_key": api_key}}}
        _save_and_reload(console, updates)
        return True

    return False


def _choose_model(console, entry: dict) -> None:
    """Let the user pick a model for the provider (optional)."""
    provider_key = entry["key"]
    models = list(entry.get("models", []))

    # Surface the currently-active model first.
    current_model = None
    try:
        current_model = get_model_router().get_model(provider_key)
    except Exception:
        current_model = None
    if current_model and current_model not in models:
        models.insert(0, current_model)
    if not models:
        return

    rows = models + ["✏️  自定义输入 Custom…"]
    start_idx = models.index(current_model) if current_model in models else 0

    def _render_model(row, is_selected: bool) -> str:
        cur = " [bold green]◀ 当前[/bold green]" if row == current_model else ""
        if is_selected:
            return f"  [bold cyan]❯[/bold cyan] [bold reverse] {row} [/bold reverse]{cur}"
        return f"     [dim]{row}[/dim]{cur}"

    midx = _arrow_menu(
        console,
        title=f"[bold cyan]🧠 选择模型 Model · {entry['label']}[/bold cyan]",
        subtitle="[dim]↑↓ 选择 · Enter 确认 · Esc 跳过[/dim]",
        rows=rows,
        render_row=_render_model,
        start_idx=start_idx,
    )
    if midx is None:
        return

    chosen = rows[midx]
    if chosen.startswith("✏️"):
        try:
            chosen = input("  Model 名称: ").strip()
        except (EOFError, KeyboardInterrupt):
            chosen = ""
        if not chosen:
            return

    # Persist + apply.
    _save_and_reload(console, {"llm": {provider_key: {"model": chosen}}}, quiet=True)
    try:
        get_model_router().set_model(chosen, provider_key)
    except Exception:
        pass


def _activate_provider(console, cli_state, provider_key: str) -> bool:
    """Switch the router + legacy engine to provider_key and persist the session."""
    try:
        router = get_model_router()
        router.reload()
        if not router.switch(provider_key):
            console.print(
                f"[red]无法切换到 {provider_key}：provider 仍未就绪。"
                "请检查 key 是否正确。[/red]\n"
            )
            return False
    except Exception as e:
        console.print(f"[red]切换失败: {e}[/red]\n")
        return False

    cli_state.current_engine = provider_key

    try:
        import asyncio
        asyncio.run(cli_state.storage.update_session(
            cli_state.session_id,
            model_choice=provider_key,
        ))
    except Exception:
        pass  # session persistence is best-effort
    return True


def _save_and_reload(console, updates: dict, quiet: bool = False) -> None:
    """Persist config updates to ~/.cktclaw/config.yaml and refresh caches."""
    try:
        from ..config_loader import save_user_config
        path = save_user_config(updates)
        if not quiet:
            console.print(f"[dim]已保存到 {path}[/dim]")
    except Exception as e:
        console.print(f"[yellow]保存配置失败: {e}[/yellow]")
    try:
        get_model_router().reload()
    except Exception:
        pass


# ━━━━━━━━━━ Helpers ━━━━━━━━━━
def _get_engine_display_name(engine: str) -> str:
    """Get user-friendly display name for an engine/provider key."""
    entry = _catalog_entry(engine)
    if entry:
        return entry["label"]
    names = {"logicrt": "LogicRT", "qwen": "Qwen"}
    return names.get(engine, engine.upper())
