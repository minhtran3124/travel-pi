"""Data-access for agent conversations, messages, and jobs (specs/travel-agent).

ORM persistence only — business logic (graph orchestration) lives in the agent
layer. Returns Pydantic schemas so the ORM stays confined to this tier.
"""

from sqlalchemy import select

from app.db import models
from app.enums import JobStatus
from app.repositories.base import Repo
from app.schemas.agent import Conversation, Job, Message


class ConversationRepository(Repo):
    """ORM-backed store of conversations, messages, and jobs."""

    # --- conversations ---
    def create_conversation(
        self,
        *,
        user_id: str,
        trip_id: str | None = None,
        title: str | None = None,
        domain: str | None = None,
    ) -> Conversation:
        row = models.Conversation(
            user_id=user_id, trip_id=trip_id, title=title, domain=domain
        )
        with self._session() as s:
            s.add(row)
            self._commit(s)
            s.refresh(row)
            return Conversation.model_validate(row)

    def get(self, id_: str) -> Conversation | None:
        with self._session() as s:
            row = s.get(models.Conversation, id_)
            return Conversation.model_validate(row) if row is not None else None

    def list_for_user(self, user_id: str) -> list[Conversation]:
        stmt = (
            select(models.Conversation)
            .where(models.Conversation.user_id == user_id)
            .order_by(models.Conversation.created_at.desc())
        )
        with self._session() as s:
            return [Conversation.model_validate(r) for r in s.scalars(stmt).all()]

    # --- messages ---
    def append_message(
        self,
        *,
        conversation_id: str,
        role: str,
        content: str = "",
        tool_calls: list | None = None,
    ) -> Message:
        row = models.Message(
            conversation_id=conversation_id,
            role=role,
            content=content,
            tool_calls=tool_calls,
        )
        with self._session() as s:
            s.add(row)
            self._commit(s)
            s.refresh(row)
            return Message.model_validate(row)

    def list_messages(self, conversation_id: str) -> list[Message]:
        stmt = (
            select(models.Message)
            .where(models.Message.conversation_id == conversation_id)
            .order_by(models.Message.created_at.asc(), models.Message.id.asc())
        )
        with self._session() as s:
            return [Message.model_validate(r) for r in s.scalars(stmt).all()]

    # --- jobs ---
    def create_job(self, *, kind: str) -> Job:
        row = models.Job(kind=kind, status=JobStatus.PENDING.value)
        with self._session() as s:
            s.add(row)
            self._commit(s)
            s.refresh(row)
            return Job.model_validate(row)

    def set_job_status(
        self,
        id_: str,
        *,
        status: JobStatus,
        result: dict | None = None,
        error: str | None = None,
    ) -> Job | None:
        with self._session() as s:
            row = s.get(models.Job, id_)
            if row is None:
                return None
            row.status = status.value
            if result is not None:
                row.result = result
            if error is not None:
                row.error = error
            self._commit(s)
            s.refresh(row)
            return Job.model_validate(row)
