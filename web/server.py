"""
Web Server — FastAPI app with WebSocket for live monitoring + chat.

WebSocket multiplexes two message streams on a single connection:
  - System events (agent spawn/stop, plugin install, etc.)
  - Chat messages (streaming LLM with tool call visualization)
"""

import asyncio
import json
import logging
import threading
import traceback
from collections import deque
from pathlib import Path
from typing import Any, Dict, List, Optional, Set

logger = logging.getLogger(__name__)

_STATIC_DIR = Path(__file__).parent / "static"
_DEFAULT_PORT = 8741

_event_queue: deque = deque(maxlen=1000)
_ws_clients: Set[Any] = set()
_chat_tasks: Dict[str, asyncio.Task] = {}


def emit_event(event_type: str, data: Dict[str, Any]) -> None:
    """Emit a system event to all connected WebSocket clients."""
    event = {
        "type": "event",
        "event_type": event_type,
        "data": data,
        "timestamp": __import__("datetime").datetime.now().isoformat(),
    }
    _event_queue.append(event)


def create_app():
    try:
        from contextlib import asynccontextmanager

        from fastapi import FastAPI, WebSocket, WebSocketDisconnect
        from fastapi.staticfiles import StaticFiles
        from fastapi.responses import HTMLResponse
    except ImportError:
        raise ImportError(
            "FastAPI required. Install: pip install 'cktclaw[web]'"
        )

    @asynccontextmanager
    async def lifespan(app_instance):
        from .bootstrap import ensure_runtime_bootstrapped
        ensure_runtime_bootstrapped()
        yield

    app = FastAPI(title="CktClaw Dashboard", version="2.0.0", lifespan=lifespan)

    if _STATIC_DIR.is_dir():
        app.mount("/static", StaticFiles(directory=str(_STATIC_DIR)), name="static")

    # ── Register API routers ──
    from .routers import register_routers
    register_routers(app)

    @app.get("/", response_class=HTMLResponse)
    async def index():
        index_path = _STATIC_DIR / "index.html"
        if index_path.is_file():
            return index_path.read_text()
        return _fallback_html()

    @app.get("/api/events")
    async def get_recent_events():
        return list(_event_queue)[-50:]

    @app.websocket("/ws")
    async def websocket_endpoint(websocket: WebSocket):
        await websocket.accept()
        _ws_clients.add(websocket)
        logger.info(f"WebSocket connected ({len(_ws_clients)} total)")

        try:
            # Send recent event history
            for event in list(_event_queue)[-20:]:
                await websocket.send_json(event)

            # Main multiplex loop — receives both chat commands and processes events
            last_event_idx = len(_event_queue)

            while True:
                # Check for new system events
                current_len = len(_event_queue)
                if current_len > last_event_idx:
                    new_events = list(_event_queue)[last_event_idx:]
                    for event in new_events:
                        await _safe_send_json(websocket, event)
                    last_event_idx = current_len

                # Non-blocking receive with timeout
                try:
                    data = await asyncio.wait_for(websocket.receive_text(), timeout=0.1)
                except asyncio.TimeoutError:
                    continue

                try:
                    msg = json.loads(data)
                except json.JSONDecodeError:
                    await _safe_send_json(websocket, {
                        "type": "chat:error", "error": "Invalid JSON"
                    })
                    continue

                msg_type = msg.get("type", "")

                if msg_type == "ping":
                    await _safe_send_json(websocket, {"type": "pong"})

                elif msg_type == "chat:send":
                    await _handle_chat_send(websocket, msg)

                elif msg_type == "chat:abort":
                    session_id = msg.get("session_id", "default")
                    task_key = f"{id(websocket)}:{session_id}"
                    task = _chat_tasks.pop(task_key, None)
                    if task and not task.done():
                        task.cancel()
                        await _safe_send_json(websocket, {
                            "type": "chat:error",
                            "session_id": session_id,
                            "error": "Aborted",
                        })

        except WebSocketDisconnect:
            pass
        except Exception:
            logger.error(f"WebSocket error: {traceback.format_exc()}")
        finally:
            _ws_clients.discard(websocket)
            # Clean up any running chat tasks for this connection
            prefix = f"{id(websocket)}:"
            for key in list(_chat_tasks):
                if key.startswith(prefix):
                    task = _chat_tasks.pop(key)
                    if not task.done():
                        task.cancel()
            logger.info(f"WebSocket disconnected ({len(_ws_clients)} remaining)")

    return app


async def _handle_chat_send(websocket, msg: dict):
    """Launch a streaming chat task for the given message."""
    from .chat_handler import stream_chat

    session_id = msg.get("session_id", "default")
    user_message = msg.get("message", "")
    use_tools = msg.get("use_tools", False)
    provider_name = msg.get("provider", None)
    attachment_ids = msg.get("attachment_ids") or []

    if not user_message.strip() and not attachment_ids:
        await _safe_send_json(websocket, {
            "type": "chat:error",
            "session_id": session_id,
            "error": "Empty message",
        })
        return

    async def _run():
        try:
            async for chunk in stream_chat(
                session_id=session_id,
                user_message=user_message,
                use_tools=use_tools,
                provider_name=provider_name,
                attachment_ids=attachment_ids,
            ):
                await _safe_send_json(websocket, chunk)
        except asyncio.CancelledError:
            await _safe_send_json(websocket, {
                "type": "chat:error",
                "session_id": session_id,
                "error": "Cancelled",
            })
        except Exception as e:
            logger.error(f"Chat task error: {traceback.format_exc()}")
            await _safe_send_json(websocket, {
                "type": "chat:error",
                "session_id": session_id,
                "error": str(e),
            })

    task = asyncio.create_task(_run())
    task_key = f"{id(websocket)}:{session_id}"
    _chat_tasks[task_key] = task


async def _safe_send_json(websocket, data: dict):
    """Send JSON to a WebSocket, ignoring disconnection errors."""
    try:
        await websocket.send_json(data)
    except Exception:
        pass


def start_web_server(port: int = _DEFAULT_PORT) -> threading.Thread:
    def _run_server():
        try:
            import uvicorn
            app = create_app()
            uvicorn.run(app, host="127.0.0.1", port=port, log_level="warning")
        except ImportError:
            logger.error("uvicorn required. Install: pip install uvicorn")
        except Exception as e:
            logger.error(f"Web server failed: {e}")

    thread = threading.Thread(target=_run_server, daemon=True)
    thread.start()
    logger.info(f"Web dashboard at http://localhost:{port}")
    return thread


def _fallback_html() -> str:
    return """<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>CktClaw Dashboard</title>
    <style>
        body { background: #1a1b26; color: #a9b1d6; font-family: 'JetBrains Mono', monospace; padding: 2rem; }
        h1 { color: #7aa2f7; }
        #events { max-height: 70vh; overflow-y: auto; background: #24283b; padding: 1rem; border-radius: 8px; }
        .event { padding: 4px 0; border-bottom: 1px solid #414868; }
        .event-type { color: #9ece6a; font-weight: bold; }
        .timestamp { color: #565f89; font-size: 0.8em; }
    </style>
</head>
<body>
    <h1>CktClaw Dashboard</h1>
    <p>Real-time monitoring + chat</p>
    <div id="status">Connecting...</div>
    <div id="events"></div>
    <script>
        const ws = new WebSocket(`ws://${location.host}/ws`);
        const eventsDiv = document.getElementById('events');
        const statusDiv = document.getElementById('status');
        ws.onopen = () => { statusDiv.textContent = '✓ Connected'; };
        ws.onclose = () => { statusDiv.textContent = '✗ Disconnected'; };
        ws.onmessage = (e) => {
            const msg = JSON.parse(e.data);
            const div = document.createElement('div');
            div.className = 'event';
            const ts = msg.timestamp ? new Date(msg.timestamp).toLocaleTimeString() : '';
            if (msg.type === 'event') {
                div.innerHTML = `<span class="timestamp">${ts}</span> <span class="event-type">[${msg.event_type}]</span> ${JSON.stringify(msg.data).slice(0, 200)}`;
            } else if (msg.type && msg.type.startsWith('chat:')) {
                div.innerHTML = `<span class="timestamp">${ts}</span> <span class="event-type">[${msg.type}]</span> ${JSON.stringify(msg).slice(0, 200)}`;
            }
            if (div.innerHTML) { eventsDiv.prepend(div); if (eventsDiv.children.length > 200) eventsDiv.lastChild.remove(); }
        };
    </script>
</body>
</html>"""
