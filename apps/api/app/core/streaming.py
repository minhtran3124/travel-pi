"""SSE streaming helper (specs/travel-agent; llm-readiness 1.2 seam).

Wraps an async generator of string chunks (or typed events) into a
Server-Sent Events response.  A terminal ``[DONE]`` event marks the end of
the stream.

Wire contract
-------------
* Token chunks (plain ``str``): ``data: <text>\\n\\n``
* Named events (``TypedSSEEvent``): ``event: <name>\\ndata: <json>\\n\\n``
* Terminal: ``data: [DONE]\\n\\n``
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from dataclasses import dataclass

from fastapi.responses import StreamingResponse


@dataclass
class TypedSSEEvent:
    """A named Server-Sent Event (``event: <name>\\ndata: <data>``)."""

    event: str
    data: str


def sse_response(chunks: AsyncIterator[str | TypedSSEEvent]) -> StreamingResponse:
    """Return a text/event-stream response.

    Plain-string chunks are emitted as default SSE events
    (``data: <chunk>``).  ``TypedSSEEvent`` instances are emitted as named
    events (``event: <name>\\ndata: <data>``).  A terminal ``[DONE]`` event
    always closes the stream.
    """

    async def event_stream() -> AsyncIterator[str]:
        async for chunk in chunks:
            if isinstance(chunk, TypedSSEEvent):
                yield f"event: {chunk.event}\ndata: {chunk.data}\n\n"
            else:
                yield f"data: {chunk}\n\n"
        yield "data: [DONE]\n\n"

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )
