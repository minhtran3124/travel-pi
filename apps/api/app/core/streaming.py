"""SSE streaming helper (specs/travel-agent; llm-readiness 1.2 seam).

Wraps an async generator of string chunks into a Server-Sent Events response —
the contract a streaming agent token feed plugs into. A terminal ``[DONE]`` event
marks the end of the stream.
"""

from __future__ import annotations

from collections.abc import AsyncIterator

from fastapi.responses import StreamingResponse


def sse_response(chunks: AsyncIterator[str]) -> StreamingResponse:
    """Return a text/event-stream response that emits each chunk as an SSE event."""

    async def event_stream() -> AsyncIterator[str]:
        async for chunk in chunks:
            yield f"data: {chunk}\n\n"
        yield "data: [DONE]\n\n"

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )
