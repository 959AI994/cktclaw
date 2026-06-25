"""
CktClaw Web Dashboard — real-time monitoring + streaming chat + management UI.
"""
from .server import create_app, start_web_server, emit_event

__all__ = ["create_app", "start_web_server", "emit_event"]
