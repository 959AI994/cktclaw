"""
Web Server — FastAPI app with WebSocket for live CLI monitoring.
"""

import asyncio
import json
import logging
import threading
from collections import deque
from pathlib import Path
from typing import Any, Dict, List, Optional, Set

logger = logging.getLogger(__name__)

_STATIC_DIR = Path(__file__).parent / "static"
_DEFAULT_PORT = 8741

# Global event bus for CLI → WebSocket
_event_queue: deque = deque(maxlen=1000)
_ws_clients: Set[Any] = set()


def emit_event(event_type: str, data: Dict[str, Any]) -> None:
    """Emit an event from CLI to all connected WebSocket clients."""
    event = {
        "type": event_type,
        "data": data,
        "timestamp": __import__("datetime").datetime.now().isoformat(),
    }
    _event_queue.append(event)


def create_app():
    """Create the FastAPI application."""
    try:
        from fastapi import FastAPI, WebSocket, WebSocketDisconnect
        from fastapi.staticfiles import StaticFiles
        from fastapi.responses import HTMLResponse
    except ImportError:
        raise ImportError(
            "FastAPI required for web dashboard. Install: pip install 'cktclaw[full]'"
        )

    app = FastAPI(title="CktClaw Dashboard", version="1.0.0")

    # Serve static files
    if _STATIC_DIR.is_dir():
        app.mount("/static", StaticFiles(directory=str(_STATIC_DIR)), name="static")

    @app.get("/", response_class=HTMLResponse)
    async def index():
        """Serve the dashboard page."""
        index_path = _STATIC_DIR / "index.html"
        if index_path.is_file():
            return index_path.read_text()
        return _fallback_html()

    @app.get("/api/status")
    async def get_status():
        """Get current agent and session status."""
        try:
            from ..agents import get_agent_runtime
            from ..tools import get_tool_registry
            from ..llm import get_model_router

            runtime = get_agent_runtime()
            registry = get_tool_registry()
            router = get_model_router()

            return {
                "agents": runtime.list_agents(),
                "tools": registry.list_names(),
                "model": router.current_name,
                "available_models": router.available_providers,
            }
        except Exception as e:
            return {"error": str(e)}

    @app.get("/api/events")
    async def get_recent_events():
        """Get recent events (fallback for non-WebSocket clients)."""
        return list(_event_queue)[-50:]

    @app.websocket("/ws")
    async def websocket_endpoint(websocket: WebSocket):
        """WebSocket endpoint for real-time event streaming."""
        await websocket.accept()
        _ws_clients.add(websocket)
        logger.info(f"WebSocket client connected ({len(_ws_clients)} total)")

        try:
            # Send recent history
            for event in list(_event_queue)[-20:]:
                await websocket.send_json(event)

            # Stream new events
            last_idx = len(_event_queue)
            while True:
                await asyncio.sleep(0.1)
                current_len = len(_event_queue)
                if current_len > last_idx:
                    new_events = list(_event_queue)[last_idx:]
                    for event in new_events:
                        await websocket.send_json(event)
                    last_idx = current_len
        except WebSocketDisconnect:
            pass
        except Exception:
            pass
        finally:
            _ws_clients.discard(websocket)
            logger.info(f"WebSocket client disconnected ({len(_ws_clients)} remaining)")

    return app


def start_web_server(port: int = _DEFAULT_PORT) -> threading.Thread:
    """
    Start the web server in a background thread.

    Returns the thread (already started).
    """
    def _run_server():
        try:
            import uvicorn
            app = create_app()
            uvicorn.run(app, host="0.0.0.0", port=port, log_level="warning")
        except ImportError:
            logger.error("uvicorn required. Install: pip install uvicorn")
        except Exception as e:
            logger.error(f"Web server failed: {e}")

    thread = threading.Thread(target=_run_server, daemon=True)
    thread.start()
    logger.info(f"Web dashboard running at http://localhost:{port}")
    return thread


def _fallback_html() -> str:
    """Minimal fallback HTML if static files are missing."""
    return """<!DOCTYPE html>
<html>
<head>
    <title>CktClaw Dashboard</title>
    <style>
        body { background: #1a1b26; color: #a9b1d6; font-family: monospace; padding: 2rem; }
        h1 { color: #7aa2f7; }
        #events { max-height: 70vh; overflow-y: auto; background: #24283b; padding: 1rem; border-radius: 8px; }
        .event { padding: 4px 0; border-bottom: 1px solid #414868; }
        .event-type { color: #9ece6a; font-weight: bold; }
        .timestamp { color: #565f89; font-size: 0.8em; }
    </style>
</head>
<body>
    <h1>CktClaw Dashboard</h1>
    <p>Real-time monitoring (read-only)</p>
    <div id="status">Connecting...</div>
    <div id="events"></div>
    <script>
        const ws = new WebSocket(`ws://${location.host}/ws`);
        const eventsDiv = document.getElementById('events');
        const statusDiv = document.getElementById('status');
        ws.onopen = () => { statusDiv.textContent = 'Connected'; };
        ws.onclose = () => { statusDiv.textContent = 'Disconnected'; };
        ws.onmessage = (e) => {
            const event = JSON.parse(e.data);
            const div = document.createElement('div');
            div.className = 'event';
            div.innerHTML = `<span class="timestamp">${event.timestamp}</span> <span class="event-type">[${event.type}]</span> ${JSON.stringify(event.data).slice(0, 200)}`;
            eventsDiv.prepend(div);
            if (eventsDiv.children.length > 200) eventsDiv.lastChild.remove();
        };
    </script>
</body>
</html>"""
