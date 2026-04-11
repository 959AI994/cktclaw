"""
UI Color and Icon Definitions

Centralized color scheme and icon mappings for consistent CLI visual appearance.
"""

from enum import Enum
from typing import Dict

# ━━━━━━━━━━ Color Definitions ━━━━━━━━━━
class Colors:
    """Standard colors used throughout CLI"""
    SUCCESS = "green"
    ERROR = "red"
    INFO = "cyan"
    WARNING = "yellow"
    STATUS = "magenta"
    HEADER = "bold cyan"
    COMMAND = "bold yellow"
    PROMPT = "bold green"
    SECTION = "bold blue"
    SUBTLE = "dim white"


# ━━━━━━━━━━ Icon Definitions ━━━━━━━━━━
class Icons:
    """Unicode icons for various operations"""
    # Loading/Progress
    LOADING = "🚀"
    SPINNER = "⠋⠙⠹⠸⠼⠴⠦⠧⠇⠏"  # Spinner animation frames

    # Status indicators
    SUCCESS = "✓"
    ERROR = "✗"
    WARNING = "⚠"
    INFO = "ℹ"

    # Domain-specific
    CIRCUIT = "⚡"
    CODE = "💾"
    MEMORY = "🧠"
    DATABASE = "🗄"
    ENGINE = "🔧"
    CLOCK = "⏱"
    LIGHTNING = "⚡"
    SPARKLE = "✨"

    # Arrows
    ARROW_RIGHT = "→"
    ARROW_LEFT = "←"
    ARROW_UP = "↑"
    ARROW_DOWN = "↓"

    # Misc
    BULLET = "•"
    DASH = "─"
    BLOCK = "█"


# ━━━━━━━━━━ Style Definitions ━━━━━━━━━━
class Styles:
    """Rich style definitions for text formatting"""
    # Headers and titles
    BANNER_TITLE = "bold cyan"
    SECTION_HEADER = "bold blue"
    SUBSECTION_HEADER = "bold cyan"

    # Commands and output
    COMMAND = "bold yellow"
    CODE = "dim white"
    KEYWORD = "bold magenta"

    # Status messages
    SUCCESS = "bold green"
    ERROR = "bold red"
    WARNING = "bold yellow"
    INFO = "bold cyan"

    # Emphasis
    HIGHLIGHT = "bold"
    SUBTLE = "dim"
    DIM = "dim white"

    # Data display
    METRIC_LABEL = "cyan"
    METRIC_VALUE = "bold green"
    METRIC_UNIT = "dim"


# ━━━━━━━━━━ Color Palette ━━━━━━━━━━
COLOR_PALETTE = {
    "success": Colors.SUCCESS,
    "error": Colors.ERROR,
    "info": Colors.INFO,
    "warning": Colors.WARNING,
    "status": Colors.STATUS,
    "header": Colors.HEADER,
    "command": Colors.COMMAND,
    "prompt": Colors.PROMPT,
    "section": Colors.SECTION,
    "subtle": Colors.SUBTLE,
}

# ━━━━━━━━━━ Icon Mappings ━━━━━━━━━━
ICON_MAP = {
    "loading": Icons.LOADING,
    "success": Icons.SUCCESS,
    "error": Icons.ERROR,
    "warning": Icons.WARNING,
    "info": Icons.INFO,
    "circuit": Icons.CIRCUIT,
    "code": Icons.CODE,
    "memory": Icons.MEMORY,
    "database": Icons.DATABASE,
    "engine": Icons.ENGINE,
    "clock": Icons.CLOCK,
    "lightning": Icons.LIGHTNING,
    "sparkle": Icons.SPARKLE,
}

# ━━━━━━━━━━ Style Map ━━━━━━━━━━
STYLE_MAP = {
    "banner_title": Styles.BANNER_TITLE,
    "section_header": Styles.SECTION_HEADER,
    "subsection_header": Styles.SUBSECTION_HEADER,
    "command": Styles.COMMAND,
    "code": Styles.CODE,
    "keyword": Styles.KEYWORD,
    "success": Styles.SUCCESS,
    "error": Styles.ERROR,
    "warning": Styles.WARNING,
    "info": Styles.INFO,
    "highlight": Styles.HIGHLIGHT,
    "subtle": Styles.SUBTLE,
    "metric_label": Styles.METRIC_LABEL,
    "metric_value": Styles.METRIC_VALUE,
}

# ━━━━━━━━━━ Operation Status Colors ━━━━━━━━━━
OPERATION_COLORS = {
    "converting": "cyan",
    "generating": "blue",
    "validating": "yellow",
    "analyzing": "magenta",
    "complete": "green",
    "failed": "red",
}

# ━━━━━━━━━━ Engine Colors ━━━━━━━━━━
ENGINE_COLORS = {
    "deepseek": "cyan",
    "local": "magenta",
    "unknown": "yellow",
}

# ━━━━━━━━━━ Status Messages ━━━━━━━━━━
STATUS_MESSAGES = {
    "converting_aig": "🚀 Converting AIG to Verilog...",
    "generating_verilog": "🚀 Generating Verilog code...",
    "validating_syntax": "✓ Validating Verilog syntax...",
    "analyzing_circuit": f"{Icons.CIRCUIT} Analyzing circuit...",
    "loading_model": f"{Icons.LOADING} Loading model...",
    "ready": f"{Icons.SUCCESS} Ready for input",
}
