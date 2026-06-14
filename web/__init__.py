"""
CktClaw Web Dashboard — real-time read-only monitoring via WebSocket.
"""

from .server import create_app, start_web_server

__all__ = ["create_app", "start_web_server"]
