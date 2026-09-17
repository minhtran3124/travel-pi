"""SSE streaming helper: wrap an async generator of string chunks or ``TypedSSEEvent`` into a text/event-stream response; the producer emits its own terminal event."""

from __future__ import annotations

from collections.abc import AsyncIterator
from dataclasses import dataclass

from fastapi.responses import StreamingResponse
from starlette.background import BackgroundTask


@dataclass
class TypedSSEEvent:
    """A named Server-Sent Event (``event: <name>\\ndata: <data>``)."""

    event: str
    data: str


def sse_response(
    chunks: AsyncIterator[str | TypedSSEEvent],
    *,
    background: BackgroundTask | None = None,
) -> StreamingResponse:
    """Return a text/event-stream response — plain strings as default ``data:`` events, ``TypedSSEEvent`` as named events; ``background`` runs after the body drains (off the reply path)."""

    async def event_stream() -> AsyncIterator[str]:
        async for chunk in chunks:
            if isinstance(chunk, TypedSSEEvent):
                yield f"event: {chunk.event}\ndata: {chunk.data}\n\n"
            else:
                # SSE forbids raw newlines in a `data:` value — emit one `data:`
                # line per physical line; the client rejoins them with `\n`.
                yield "".join(f"data: {line}\n" for line in chunk.split("\n")) + "\n"

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
        background=background,
    )
