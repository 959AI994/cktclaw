"""Tests for MCP initialize handshake."""
import json
import threading
import pytest
from unittest.mock import MagicMock, patch


def _make_mock_proc(response=None, crash=False):
    response = response or {"jsonrpc": "2.0", "id": 1, "result": {"capabilities": {}}}
    response_line = json.dumps(response) + "\n"

    class FakeStdin:
        def write(self, data): pass
        def flush(self): pass

    class FakeStdout:
        def __init__(self): self._called = False
        def readline(self):
            if crash:
                raise IOError("pipe broken")
            if not self._called:
                self._called = True
                return response_line
            return ""

    proc = MagicMock()
    proc.stdin = FakeStdin()
    proc.stdout = FakeStdout()
    proc.poll = MagicMock(return_value=None)
    proc.terminate = MagicMock()
    proc.wait = MagicMock(return_value=0)
    return proc


def test_handshake_success():
    from cktclaw.mcp.mcp_manager import MCPServerHandle
    handle = MCPServerHandle("test-mcp", _make_mock_proc(), {})
    assert handle.send_initialize(timeout=2.0) is True


def test_handshake_crash_returns_false():
    from cktclaw.mcp.mcp_manager import MCPServerHandle
    handle = MCPServerHandle("test-mcp", _make_mock_proc(crash=True), {})
    assert handle.send_initialize(timeout=1.0) is False


def test_handshake_dead_proc_returns_false():
    from cktclaw.mcp.mcp_manager import MCPServerHandle
    proc = MagicMock()
    proc.poll = MagicMock(return_value=1)
    handle = MCPServerHandle("test-mcp", proc, {})
    assert handle.send_initialize(timeout=1.0) is False


def test_start_server_returns_false_on_failed_handshake():
    from cktclaw.mcp.mcp_manager import MCPServerManager
    mgr = MCPServerManager.__new__(MCPServerManager)
    mgr._servers = {"abc-mcp": {"command": "abc-mcp", "args": [], "env": {}}}
    mgr._handles = {}
    mgr._lock = threading.Lock()
    with patch("subprocess.Popen", return_value=_make_mock_proc(crash=True)):
        result = mgr.start_server("abc-mcp", handshake_timeout=1.0)
    assert result is False and "abc-mcp" not in mgr._handles


def test_start_server_keeps_handle_after_success():
    from cktclaw.mcp.mcp_manager import MCPServerManager
    mgr = MCPServerManager.__new__(MCPServerManager)
    mgr._servers = {"yosys-mcp": {"command": "yosys-mcp", "args": [], "env": {}}}
    mgr._handles = {}
    mgr._lock = threading.Lock()
    with patch("subprocess.Popen", return_value=_make_mock_proc()):
        result = mgr.start_server("yosys-mcp", handshake_timeout=2.0)
    assert result is True and "yosys-mcp" in mgr._handles
