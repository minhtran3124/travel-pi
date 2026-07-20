"""Agent-layer schemas (specs/travel-agent).

Entity schemas the repository returns so the ORM stays confined to
``repositories/`` (built straight from rows via ``from_attributes``). Request /
response schemas for the ``/agent`` endpoints are added in Phase 6.
"""

from typing import Any

from pydantic import Field, model_validator

from app.enums import JobStatus, MessageRole
from app.schemas.base import AppBaseModel


class ChatRequest(AppBaseModel):
    """A turn of input to the agent."""

    message: str | None = Field(
        default=None, min_length=1, description="The traveller's message."
    )
    user_id: str = Field(description="Caller identity (no auth enforced).")
    trip_id: str | None = Field(
        default=None, description="Optional trip context for the agent."
    )
    conversation_id: str | None = Field(
        default=None, description="Existing conversation to continue; None starts one."
    )
    retry: bool = Field(
        default=False,
        description="Re-answer the last (unanswered) user turn without re-saving "
        "it — used when a previous turn was interrupted before the assistant "
        "reply was persisted. Requires conversation_id + message.",
    )
    resume: Any = Field(
        default=None,
        description="Resume value for a HITL plan-approval interrupt. "
        "Pass {'approved': true} to confirm or {'approved': false} to cancel. "
        "Requires conversation_id.",
    )
    timezone: str | None = Field(
        default=None,
        description="Traveller's IANA timezone (e.g. 'Asia/Ho_Chi_Minh') detected by the "
        "client via Intl.DateTimeFormat().resolvedOptions().timeZone. Used to ground "
        "relative dates like 'tomorrow'. Invalid or missing falls back to the server default.",
    )

    @model_validator(mode="after")
    def _require_message_or_resume(self) -> "ChatRequest":
        if self.resume is None and not self.message:
            raise ValueError("Either 'message' or 'resume' must be provided.")
        return self


class ChatResponse(AppBaseModel):
    """The agent's reply for one turn."""

    conversation_id: str
    reply: str
    trip_id: str | None = Field(
        default=None,
        description="The active trip after this turn — echoes the request's "
        "trip_id, or a new id when the agent opened one via create_trip. "
        "Informational only (e.g. to display or link to the trip) — do NOT "
        "resend this as the next request's trip_id just because it changed "
        "here: the server derives the LangGraph thread key from the "
        "request's trip_id, so echoing a create_trip-opened id back would "
        "fork the conversation onto a fresh, empty thread. Only pass an "
        "explicit trip_id when the user has actually navigated to that "
        "trip's own page; otherwise keep sending whatever this "
        "conversation started with (including null) and the server keeps "
        "the active trip current on its own.",
    )
    current_flow: str | None = None
    suggestions: list[str] = Field(default_factory=list)
    interrupt_pending: bool = False
    interrupt_payload: dict | None = None


class ToolManifestEntry(AppBaseModel):
    name: str
    description: str
    read_only: bool
    destructive: bool


class AgentManifest(AppBaseModel):
    """Agent capability manifest for clients (roadmap B4)."""

    subagents: list[str]
    tools: list[ToolManifestEntry]


class Message(AppBaseModel):
    id: str
    conversation_id: str
    role: MessageRole
    content: str
    tool_calls: list | None = None
    created_at: str


class Conversation(AppBaseModel):
    id: str
    user_id: str
    trip_id: str | None = None
    title: str | None = None
    domain: str | None = None
    created_at: str
    updated_at: str


class ClaimRequest(AppBaseModel):
    """Request body for POST /agent/conversations/claim."""

    anonymous_user_id: str


class ClaimResult(AppBaseModel):
    """Response for POST /agent/conversations/claim."""

    claimed: int


class Job(AppBaseModel):
    id: str
    kind: str
    status: JobStatus
    result: dict | None = None
    error: str | None = None
    created_at: str
    updated_at: str
