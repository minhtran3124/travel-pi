"""Request/response schemas for the trip-research agent surface (design §5).

Bodies carry projected state only — a run id, a status, a dossier file index and
file text a user edits; never message text, tool arguments or LLM output.
"""

from __future__ import annotations

from pydantic import Field

from app.schemas.base import AppBaseModel


class ResearchStartRequest(AppBaseModel):
    """Body of ``POST /agent/trips/{trip_id}/research`` (and ``/revise``)."""

    instruction: str | None = Field(
        default=None,
        description="Optional free-text steer; PII-redacted before it becomes a turn.",
    )
    language: str | None = Field(
        default=None,
        description="Optional reply language; defaults to English when omitted.",
    )


class ResearchStartResponse(AppBaseModel):
    """202 reply: the booked run and its turn on the dossier thread."""

    run_id: str
    thread_turn: int = Field(
        description="1 for the first run on the trip, N for the Nth revise turn.",
    )


class ResearchStatusResponse(AppBaseModel):
    """A research run's projected state — status, dossier index and proposal flag."""

    run_id: str
    trip_id: str | None
    status: str
    thread_turn: int
    files: list[str]
    proposal_ready: bool


class ResearchFileContent(AppBaseModel):
    """One dossier file's text, addressed by its route-prefixed path."""

    path: str
    content: str


class ResearchFileWrite(AppBaseModel):
    """Body of ``PUT /agent/research/{run_id}/files/{path}`` — a user edit."""

    content: str
