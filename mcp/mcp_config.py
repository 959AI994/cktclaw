"""
MCP Configuration Generator — reads template JSON snippets from
digital-chip-design-agents and resolves placeholder paths to absolute paths
based on the current machine's tool manifest.
"""

import json
import os
from pathlib import Path
from typing import Optional

from ..eda_tools.tool_detection import ToolManifest

_CKTCLAW_DIR = Path(__file__).parent.parent.resolve()
_PROJECT_ROOT = _CKTCLAW_DIR.parent

_TEMPLATES_DIR = Path(os.environ.get(
    "CHIP_AGENTS_ROOT",
    str(_PROJECT_ROOT / "digital-chip-design-agents" / "plugins"),
)) / "infrastructure" / "mcp"
_ADAPTER_PATH = _CKTCLAW_DIR / "mcp" / "mcp-adapter.py"
_SESSION_ADAPTER_PATH = _CKTCLAW_DIR / "mcp" / "mcp-session-adapter.py"
_WRAPPERS_DIR = _CKTCLAW_DIR / "eda_tools" / "wrappers"

_PLACEHOLDER = "/absolute/path/to"

# Maps template file name → required tool name for availability check
_TEMPLATE_TOOL_MAP: dict[str, str] = {
    "mcp-yosys.json":            "yosys",
    "mcp-opensta.json":          "opensta",
    "mcp-opensta-session.json":  "opensta",
    "mcp-openroad.json":         "openroad",
    "mcp-openroad-session.json": "openroad",
    "mcp-verilator.json":        "verilator",
    "mcp-klayout.json":          "klayout",
    "mcp-bambu.json":            "bambu-hls",
    "mcp-gem5.json":             "gem5",
    "mcp-symbiflow.json":        "symbiyosys",
}

# Maps template file → whether it uses mcp-session-adapter (True) or mcp-adapter (False)
_SESSION_TEMPLATES: set[str] = {
    "mcp-opensta-session.json",
    "mcp-openroad-session.json",
}


def _resolve_paths(raw: str) -> str:
    """Replace placeholder paths with real absolute paths."""
    result = raw
    result = result.replace(
        f"{_PLACEHOLDER}/plugins/infrastructure/tools/mcp-adapter.py",
        str(_ADAPTER_PATH),
    )
    result = result.replace(
        f"{_PLACEHOLDER}/plugins/infrastructure/tools/mcp-session-adapter.py",
        str(_SESSION_ADAPTER_PATH),
    )
    for wrapper in _WRAPPERS_DIR.glob("wrap-*.sh"):
        placeholder_wrapper = f"{_PLACEHOLDER}/plugins/infrastructure/tools/{wrapper.name}"
        result = result.replace(placeholder_wrapper, str(wrapper))
    # Catch any remaining placeholders
    result = result.replace(_PLACEHOLDER, str(_CKTCLAW_DIR))
    return result


def generate_mcp_configs(
    manifest: ToolManifest,
    templates_dir: Optional[Path] = None,
) -> dict[str, dict]:
    """
    Read MCP template JSON files and produce resolved configs for available tools.

    Returns dict mapping server name → full mcpServer config dict.
    """
    tdir = templates_dir or _TEMPLATES_DIR
    if not tdir.is_dir():
        return {}

    servers: dict[str, dict] = {}

    for template_file in sorted(tdir.glob("*.json")):
        tool_name = _TEMPLATE_TOOL_MAP.get(template_file.name)
        if tool_name and not manifest.is_tool_available(tool_name):
            continue

        raw = template_file.read_text()
        resolved = _resolve_paths(raw)
        try:
            data = json.loads(resolved)
        except json.JSONDecodeError:
            continue

        mcp_block = data.get("mcpServers", {})
        servers.update(mcp_block)

    return servers


def write_claude_settings(servers: dict[str, dict], output_path: Path) -> None:
    """Write .claude/settings.json with mcpServers block."""
    existing: dict = {}
    if output_path.exists():
        try:
            existing = json.loads(output_path.read_text())
        except (json.JSONDecodeError, OSError):
            pass

    existing["mcpServers"] = servers
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(existing, indent=2, ensure_ascii=False))


def write_internal_mcp_config(servers: dict[str, dict], output_path: Path) -> None:
    """Write cktclaw/mcp/mcp-servers.json for internal use."""
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(servers, indent=2, ensure_ascii=False))
