"""Data-access for agent conversations, messages, and jobs (specs/travel-agent).

ORM persistence only — business logic (graph orchestration) lives in the agent
layer. Returns Pydantic schemas so the ORM stays confined to this tier.
"""

from sqlalchemy import func, select

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

    def ensure_conversation(
        self,
        *,
        conversation_id: str | None,
        user_id: str,
        trip_id: str | None = None,
    ) -> str:
        """Return a conversation id that is guaranteed to have a row.

        Get-or-create: when ``conversation_id`` is None a fresh row is created;
        when it is supplied (e.g. a client-minted id, or one restored from the
        browser across reloads) the row is created with that explicit id if it
        does not exist yet. This prevents orphaned messages — a message must
        never reference a conversation that is absent from this table — and
        self-heals ids minted before this guard existed.
        """
        if conversation_id is None:
            return self.create_conversation(user_id=user_id, trip_id=trip_id).id
        with self._session() as s:
            if s.get(models.Conversation, conversation_id) is None:
                s.add(
                    models.Conversation(
                        id=conversation_id, user_id=user_id, trip_id=trip_id
                    )
                )
                self._commit(s)
        return conversation_id

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

    def count_user_turns_since(self, user_id: str, iso_cutoff: str) -> int:
        """Count user-role messages for *user_id* on or after *iso_cutoff*.

        Joins messages → conversations on conversation_id so no additional FK is
        needed. ISO-8601 strings sort chronologically, so a ``>=`` string
        comparison yields the correct day-boundary cutoff.
        """
        stmt = (
            select(func.count())
            .select_from(models.Message)
            .join(
                models.Conversation,
                models.Message.conversation_id == models.Conversation.id,
            )
            .where(models.Conversation.user_id == user_id)
            .where(models.Message.role == "user")
            .where(models.Message.created_at >= iso_cutoff)
        )
        with self._session() as s:
            return s.scalar(stmt) or 0

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
