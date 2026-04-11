"""UI module for LogicRT CLI"""

from .colors import Colors, Icons, Styles, COLOR_PALETTE, ICON_MAP, STYLE_MAP
from .renderer import (
    create_console,
    render_spinner,
    render_progress,
    render_verilog_code,
    render_analysis_report,
    render_metrics_table,
    render_completion_summary,
    render_error,
    render_success,
    render_session_info,
    render_header,
    render_divider,
    render_turn_separator,
    render_aig_processing,
    render_prompt,
    render_user_message,
    render_assistant_message,
    format_time,
    format_size,
)

__all__ = [
    # Colors and styles
    "Colors",
    "Icons",
    "Styles",
    "COLOR_PALETTE",
    "ICON_MAP",
    "STYLE_MAP",
    # Renderer functions
    "create_console",
    "render_spinner",
    "render_progress",
    "render_verilog_code",
    "render_analysis_report",
    "render_metrics_table",
    "render_completion_summary",
    "render_error",
    "render_success",
    "render_session_info",
    "render_header",
    "render_divider",
    "render_turn_separator",
    "render_aig_processing",
    "render_prompt",
    "render_user_message",
    "render_assistant_message",
    "format_time",
    "format_size",
]
