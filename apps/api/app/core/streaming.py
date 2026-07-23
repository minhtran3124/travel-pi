"""SSE streaming helper (specs/travel-agent; llm-readiness 1.2 seam).

Wraps an async generator of string chunks (or typed events) into a
Server-Sent Events response.  A terminal ``[DONE]`` event marks the end of
the stream.

Wire contract
-------------
* Token chunks (plain ``str``): ``data: <text>\\n\\n``
* Named events (``TypedSSEEvent``): ``event: <name>\\ndata: <json>\\n\\n``

The agent stream is fully typed (see ``app.streaming.events``); the terminal is
an explicit ``event: done`` emitted by the producer, not a ``[DONE]`` sentinel
appended here.
"""

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
    """Return a text/event-stream response.

    Plain-string chunks are emitted as default SSE events
    (``data: <chunk>``).  ``TypedSSEEvent`` instances are emitted as named
    events (``event: <name>\\ndata: <data>``). The producer is responsible for
    emitting its own terminal event (the agent stream uses ``event: done``).

    :param chunks: An async iterator of plain-text chunks or typed SSE events.
    :param background: Optional Starlette background task run by the ASGI
        server after the response body has fully drained — used to schedule
        post-stream work (e.g. memory extraction) off the reply path.
    :return: A ``text/event-stream`` streaming response.
    """

    async def event_stream() -> AsyncIterator[str]:
        async for chunk in chunks:
            if isinstance(chunk, TypedSSEEvent):
                yield f"event: {chunk.event}\ndata: {chunk.data}\n\n"
            else:
                # SSE forbids raw newlines inside a `data:` value — a chunk that
                # contains them (markdown paragraph breaks, list separators) must
                # be emitted as one `data:` line per physical line. The client
                # rejoins them with `\n`, preserving the markdown structure.
                yield "".join(f"data: {line}\n" for line in chunk.split("\n")) + "\n"

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
        background=background,
    )
