"""
Streaming renderer — token-by-token display using Rich.
"""

import asyncio
from typing import AsyncGenerator, Callable, Optional

from rich.console import Console
from rich.live import Live
from rich.markdown import Markdown
from rich.text import Text

from .types import StreamChunk


class StreamingRenderer:
    """
    Renders streaming LLM output to terminal using Rich Live.

    Features:
    - Token-by-token display
    - Markdown rendering on completion
    - Tool call notifications
    """

    def __init__(self, console: Optional[Console] = None):
        self.console = console or Console()
        self._buffer = ""
        self._tool_calls_pending = 0

    async def render_stream(
        self,
        stream: AsyncGenerator[StreamChunk, None],
        on_tool_call: Optional[Callable] = None,
    ) -> str:
        """
        Render a streaming response to the terminal.

        Args:
            stream: Async generator of StreamChunks.
            on_tool_call: Optional callback when a tool call is detected.

        Returns:
            Complete text content of the response.
        """
        self._buffer = ""
        tool_calls = []

        with Live(
            Text("", style="dim"),
            console=self.console,
            refresh_per_second=15,
            transient=True,
        ) as live:
            async for chunk in stream:
                if chunk.text_delta:
                    self._buffer += chunk.text_delta
                    # Show raw text during streaming (fast updates)
                    live.update(Text(self._buffer))

                if chunk.tool_call_delta and chunk.tool_call_delta.is_complete:
                    tc = chunk.tool_call_delta
                    tool_calls.append({
                        "id": tc.id,
                        "name": tc.name,
                        "arguments": tc.arguments,
                    })
                    if on_tool_call:
                        on_tool_call(tc)

                if chunk.is_done:
                    break

        # Final render as Markdown
        if self._buffer.strip():
            self.console.print(Markdown(self._buffer))

        # Report tool calls
        if tool_calls:
            for tc in tool_calls:
                self.console.print(
                    f"  [dim]→ Calling tool:[/dim] [bold cyan]{tc['name']}[/bold cyan]"
                )

        return self._buffer

    async def render_stream_simple(
        self,
        stream: AsyncGenerator[StreamChunk, None],
    ) -> str:
        """Simple render without Rich Live (for non-TTY or testing)."""
        buffer = ""
        async for chunk in stream:
            if chunk.text_delta:
                buffer += chunk.text_delta
            if chunk.is_done:
                break
        return buffer
