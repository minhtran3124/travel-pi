"""SSE wire-encoding unit tests for app.core.streaming.

Regression guard: a token chunk that contains newlines (markdown paragraph
breaks before a heading, blank lines between list groups) must be encoded as
one ``data:`` line per physical line — never a single ``data:`` with raw
newlines, which SSE framing would swallow and break markdown structure.
"""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator

from app.core.streaming import TypedSSEEvent, sse_response


def _collect(chunks: list[str | TypedSSEEvent]) -> str:
    async def run() -> str:
        async def gen() -> AsyncIterator[str | TypedSSEEvent]:
            for c in chunks:
                yield c

        resp = sse_response(gen())
        body = b""
        async for part in resp.body_iterator:
            body += part if isinstance(part, bytes) else part.encode()
        return body.decode()

    return asyncio.run(run())


def _client_reconstruct(wire: str) -> list[str]:
    """Mirror of the frontend parseSSE: rejoin a block's data: lines with \\n."""
    out: list[str] = []
    for block in wire.split("\n\n"):
        if not block:
            continue
        data_lines = [
            ln[len("data: ") :] for ln in block.split("\n") if ln.startswith("data: ")
        ]
        out.append("\n".join(data_lines))
    return out


def test_multiline_chunk_is_split_into_data_lines():
    wire = _collect(["foo\n\n### Forecast"])
    # The blank line before the heading is encoded, not swallowed.
    assert "data: foo\ndata: \ndata: ### Forecast\n\n" in wire


def test_client_reconstructs_original_markdown():
    chunk = "PM10: 43.8\n\n### Forecast\n- June 27"
    wire = _collect([chunk])
    reconstructed = _client_reconstruct(wire)
    assert reconstructed[0] == chunk  # round-trips exactly


def test_plain_chunk_unchanged():
    # No [DONE] sentinel: the producer emits its own terminal (event: done).
    wire = _collect(["hello"])
    assert wire == "data: hello\n\n"


def test_typed_event_unchanged():
    wire = _collect([TypedSSEEvent(event="interrupt", data='{"a":1}')])
    assert 'event: interrupt\ndata: {"a":1}\n\n' in wire
