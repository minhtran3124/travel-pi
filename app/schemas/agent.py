"""Agent-layer schemas (specs/travel-agent).

Entity schemas the repository returns so the ORM stays confined to
``repositories/`` (built straight from rows via ``from_attributes``). Request /
response schemas for the ``/agent`` endpoints are added in Phase 6.
"""

from app.enums import JobStatus, MessageRole
from app.schemas.base import AppBaseModel


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


class Job(AppBaseModel):
    id: str
    kind: str
    status: JobStatus
    result: dict | None = None
    error: str | None = None
    created_at: str
    updated_at: str
