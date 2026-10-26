"""Per-process cap on in-flight chat-model calls, so N concurrent chats cannot exceed provider RPM/TPM.

Attached as a callback on real chat models only (``_build_chat_model``); ``FakeLLM`` never
passes through it, so tests are unaffected. The slot is held from model start to end/error,
which covers the whole streamed response. Async-only: a sync ``invoke`` is not bounded.
"""

from __future__ import annotations

import asyncio
import weakref
from typing import Any
from uuid import UUID

from langchain_core.callbacks import AsyncCallbackHandler

# One semaphore per event loop (asyncio primitives bind to a loop); in prod there is one.
_semaphores: weakref.WeakKeyDictionary[asyncio.AbstractEventLoop, asyncio.Semaphore] = (
    weakref.WeakKeyDictionary()
)


def _semaphore(limit: int) -> asyncio.Semaphore:
    loop = asyncio.get_running_loop()
    sem = _semaphores.get(loop)
    if sem is None:
        sem = _semaphores[loop] = asyncio.Semaphore(limit)
    return sem


def reset_limiter() -> None:
    """Drop cached semaphores (tests / settings reload)."""
    _semaphores.clear()


class LLMConcurrencyLimiter(AsyncCallbackHandler):
    """Holds one semaphore slot per in-flight chat-model run."""

    run_inline = True  # await acquire before the model call proceeds

    def __init__(self, limit: int) -> None:
        self.limit = limit
        self._held: set[UUID] = set()

    async def on_chat_model_start(
        self,
        serialized: dict[str, Any],
        messages: Any,
        *,
        run_id: UUID,
        **kwargs: Any,
    ) -> None:
        await _semaphore(self.limit).acquire()
        self._held.add(run_id)

    def _release(self, run_id: UUID) -> None:
        if run_id in self._held:  # idempotent: end and error may both fire
            self._held.discard(run_id)
            _semaphore(self.limit).release()

    async def on_llm_end(self, response: Any, *, run_id: UUID, **kwargs: Any) -> None:
        self._release(run_id)

    async def on_llm_error(
        self, error: BaseException, *, run_id: UUID, **kwargs: Any
    ) -> None:
        self._release(run_id)
