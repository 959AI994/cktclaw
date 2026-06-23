"""
YAML Configuration Loader — external config file support.

Loads settings from ~/.cktclaw/config.yaml with fallback to defaults in config.py.
Generates a default config file on first run if it doesn't exist.
"""

import logging
import os
from pathlib import Path
from typing import Any, Dict, Optional

logger = logging.getLogger(__name__)

# Config file location
DEFAULT_CONFIG_DIR = Path.home() / ".cktclaw"
DEFAULT_CONFIG_FILE = DEFAULT_CONFIG_DIR / "config.yaml"

# Default configuration template
DEFAULT_CONFIG_TEMPLATE = """\
# CktClaw Configuration
# Generated automatically. Edit to customize behavior.
# Documentation: https://github.com/cktclaw/cktclaw#configuration

# ━━━━━━━━━━ LLM Providers ━━━━━━━━━━
llm:
  default_provider: deepseek
  # Provider failover order (used when primary fails)
  failover_chain:
    - deepseek
    - claude
    - openai

  deepseek:
    # api_key: sk-... (prefer DEEPSEEK_API_KEY env var)
    base_url: https://api.deepseek.com
    model: deepseek-chat
    timeout: 120
    temperature: 0.3
    max_tokens: 4096

  claude:
    # api_key: sk-ant-... (prefer ANTHROPIC_API_KEY env var)
    model: claude-sonnet-4-6
    max_tokens: 4096

  openai:
    # api_key: sk-... (prefer OPENAI_API_KEY env var)
    base_url: https://api.openai.com/v1
    model: gpt-4o
    max_tokens: 4096

# ━━━━━━━━━━ Tool Guardrails ━━━━━━━━━━
guardrails:
  max_duplicate_calls: 3
  max_output_chars: 8000
  per_turn_tool_limit: 30

# ━━━━━━━━━━ Agent / Delegation ━━━━━━━━━━
agent:
  max_turns: 12
  sub_agent_max_turns: 10
  sub_agent_max_tokens: 50000
  sub_agent_max_tool_calls: 30

# ━━━━━━━━━━ Context & Memory ━━━━━━━━━━
context:
  max_memory_rounds: 5
  context_window_size: 16384

# ━━━━━━━━━━ Trajectory Logging ━━━━━━━━━━
trajectory:
  enabled: true
  directory: .cktclaw/trajectories

# ━━━━━━━━━━ External Agent Skills ━━━━━━━━━━
skills:
  # Codex-style SKILL.md search paths (absolute paths recommended).
  # Skill runtimes live in deps/ (verilog-generator, FPGA-Agent-skills) — see setup.sh.
  # Also scanned: ~/.cktclaw/skills/
  # Env override: CKTCLAW_SKILL_PATHS (colon-separated).
  search_paths: []
  # Example external full clone (runtime/scripts — optional):
  # search_paths:
  #   - /path/to/verilog-generator

# ━━━━━━━━━━ Security ━━━━━━━━━━
security:
  # Restrict file operations to these directories (empty = no restriction)
  allowed_paths: []
  # Block these path patterns
  blocked_patterns:
    - /etc/
    - /root/.ssh/

# ━━━━━━━━━━ UI ━━━━━━━━━━
ui:
  syntax_theme: monokai
  spinner_color: cyan
"""


def _load_yaml(filepath: Path) -> Dict[str, Any]:
    """Load a YAML file. Returns empty dict if yaml is unavailable or file is invalid."""
    try:
        import yaml
    except ImportError:
        logger.debug("PyYAML not installed; skipping config file loading")
        return {}

    try:
        with open(filepath, "r", encoding="utf-8") as f:
            data = yaml.safe_load(f)
            return data if isinstance(data, dict) else {}
    except FileNotFoundError:
        return {}
    except Exception as e:
        logger.warning(f"Failed to parse config file {filepath}: {e}")
        return {}


def ensure_config_file() -> Path:
    """Create default config file if it doesn't exist. Returns the config path."""
    config_path = DEFAULT_CONFIG_FILE
    if not config_path.exists():
        try:
            config_path.parent.mkdir(parents=True, exist_ok=True)
            config_path.write_text(DEFAULT_CONFIG_TEMPLATE, encoding="utf-8")
            logger.info(f"Created default config at {config_path}")
        except OSError as e:
            logger.debug(f"Could not create config file: {e}")
    return config_path


class CktClawConfig:
    """
    Unified configuration with YAML file support + fallback to defaults.

    Priority: Environment variables > YAML config > Python defaults
    """

    def __init__(self, config_path: Optional[Path] = None):
        self._config_path = config_path or DEFAULT_CONFIG_FILE
        self._data: Dict[str, Any] = {}
        self._loaded = False

    def load(self) -> None:
        """Load configuration from YAML file."""
        if self._loaded:
            return
        self._data = _load_yaml(self._config_path)
        self._loaded = True

    def get(self, dotted_key: str, default: Any = None) -> Any:
        """
        Get a config value by dotted path (e.g., 'guardrails.max_output_chars').

        Falls back to default if key not found.
        """
        self.load()
        keys = dotted_key.split(".")
        value = self._data
        for key in keys:
            if isinstance(value, dict):
                value = value.get(key)
            else:
                return default
            if value is None:
                return default
        return value

    def get_int(self, dotted_key: str, default: int = 0) -> int:
        """Get an integer config value."""
        val = self.get(dotted_key, default)
        try:
            return int(val)
        except (TypeError, ValueError):
            return default

    def get_str(self, dotted_key: str, default: str = "") -> str:
        """Get a string config value."""
        val = self.get(dotted_key, default)
        return str(val) if val is not None else default

    def get_bool(self, dotted_key: str, default: bool = False) -> bool:
        """Get a boolean config value."""
        val = self.get(dotted_key, default)
        if isinstance(val, bool):
            return val
        if isinstance(val, str):
            return val.lower() in ("true", "1", "yes")
        return default

    def get_list(self, dotted_key: str, default: Optional[list] = None) -> list:
        """Get a list config value."""
        val = self.get(dotted_key, default)
        if isinstance(val, list):
            return val
        return default or []

    @property
    def raw(self) -> Dict[str, Any]:
        """Access the raw config dict."""
        self.load()
        return self._data

    # ━━━━━━━━━━ Convenience accessors ━━━━━━━━━━

    @property
    def guardrails_max_duplicates(self) -> int:
        return self.get_int("guardrails.max_duplicate_calls", 3)

    @property
    def guardrails_max_output(self) -> int:
        return self.get_int("guardrails.max_output_chars", 8000)

    @property
    def guardrails_per_turn_limit(self) -> int:
        return self.get_int("guardrails.per_turn_tool_limit", 30)

    @property
    def agent_max_turns(self) -> int:
        return self.get_int("agent.max_turns", 12)

    @property
    def trajectory_enabled(self) -> bool:
        return self.get_bool("trajectory.enabled", True)

    @property
    def trajectory_directory(self) -> str:
        return self.get_str("trajectory.directory", ".cktclaw/trajectories")

    @property
    def failover_chain(self) -> list:
        return self.get_list("llm.failover_chain", ["deepseek", "claude", "openai"])

    @property
    def default_provider(self) -> str:
        return self.get_str("llm.default_provider", "deepseek")

    @property
    def security_allowed_paths(self) -> list:
        return self.get_list("security.allowed_paths", [])

    @property
    def security_blocked_patterns(self) -> list:
        return self.get_list("security.blocked_patterns", ["/etc/", "/root/.ssh/"])


# Global singleton
_config: Optional[CktClawConfig] = None


def get_config(config_path: Optional[Path] = None) -> CktClawConfig:
    """Get or create the global CktClawConfig instance."""
    global _config
    if _config is None:
        _config = CktClawConfig(config_path=config_path)
    return _config


def reset_config_cache() -> None:
    """Drop the cached config so the next get_config() re-reads from disk.

    Call this after writing ~/.cktclaw/config.yaml at runtime (e.g. when the user
    saves a new API key via /model) so the change is picked up immediately.
    """
    global _config
    _config = None


def save_user_config(updates: Dict[str, Any]) -> Path:
    """Deep-merge ``updates`` into ~/.cktclaw/config.yaml and persist it.

    Returns the path written. Resets the in-memory config cache so subsequent
    reads see the new values.
    """
    import yaml

    path = DEFAULT_CONFIG_FILE
    path.parent.mkdir(parents=True, exist_ok=True)

    existing: Dict[str, Any] = {}
    if path.exists():
        try:
            with open(path, "r", encoding="utf-8") as fh:
                existing = yaml.safe_load(fh) or {}
        except Exception:
            existing = {}

    def _deep_merge(base: Dict[str, Any], extra: Dict[str, Any]) -> Dict[str, Any]:
        for k, v in extra.items():
            if isinstance(v, dict) and isinstance(base.get(k), dict):
                base[k] = _deep_merge(base[k], v)
            else:
                base[k] = v
        return base

    merged = _deep_merge(existing, updates)
    with open(path, "w", encoding="utf-8") as fh:
        yaml.safe_dump(merged, fh, allow_unicode=True, sort_keys=False)

    try:
        os.chmod(path, 0o600)
    except Exception:
        pass

    reset_config_cache()
    return path
