"""Data-access for agent conversations, messages, and jobs; graph orchestration lives in the agent layer."""

from sqlalchemy import func, select, update

from app.db import models
from app.enums import JobStatus
from app.repositories.base import Repo
from app.schemas.agent import Conversation, Job, Message
from app.schemas.feedback import MessageForFeedback


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
        """Get-or-create: return a conversation id guaranteed to have a row, creating one (with the supplied id if given) so a message never references an absent conversation."""
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

    def reassign_user(self, *, from_user_id: str, to_user_id: str) -> int:
        """Reassign everything owned by *from_user_id* to *to_user_id* — conversations, agent_runs and feedback_events in one transaction (messages follow via conversation_id)."""
        with self._session() as s:
            result = s.execute(
                update(models.Conversation)
                .where(models.Conversation.user_id == from_user_id)
                .values(user_id=to_user_id)
            )
            for model in (models.AgentRun, models.FeedbackEvent):
                s.execute(
                    update(model)
                    .where(model.user_id == from_user_id)
                    .values(user_id=to_user_id)
                )
            self._commit(s)
            return result.rowcount

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
        message_id: str | None = None,
        agent_run_id: str | None = None,
    ) -> Message:
        """Insert one message row. ``message_id`` reuses an id already sent to the client; ``agent_run_id`` links the producing run (None for user turns)."""
        row = models.Message(
            conversation_id=conversation_id,
            role=role,
            content=content,
            tool_calls=tool_calls,
            agent_run_id=agent_run_id,
        )
        if message_id is not None:
            row.id = message_id
        with self._session() as s:
            s.add(row)
            self._commit(s)
            s.refresh(row)
            return Message.model_validate(row)

    def get_message_for_feedback(self, message_id: str) -> MessageForFeedback | None:
        """Load a message with its conversation owner and linked run status in one query (rateability is decided by the feedback service)."""
        stmt = (
            select(
                models.Message.id,
                models.Message.conversation_id,
                models.Message.role,
                models.Message.agent_run_id,
                models.Conversation.user_id.label("owner_user_id"),
                models.AgentRun.status.label("run_status"),
            )
            .join(
                models.Conversation,
                models.Message.conversation_id == models.Conversation.id,
            )
            .outerjoin(
                models.AgentRun, models.Message.agent_run_id == models.AgentRun.id
            )
            .where(models.Message.id == message_id)
        )
        with self._session() as s:
            row = s.execute(stmt).first()
            return MessageForFeedback.model_validate(row) if row is not None else None

    def run_status_for_messages(
        self, message_ids: list[str]
    ) -> dict[str, tuple[str | None, str | None]]:
        """Bulk ``(agent_run_id, run_status)`` per message id in one query (avoids an N+1); no linked run maps to ``(None, None)``, a missing run to ``(run_id, None)``."""
        if not message_ids:
            return {}
        stmt = (
            select(
                models.Message.id,
                models.Message.agent_run_id,
                models.AgentRun.status,
            )
            .outerjoin(
                models.AgentRun, models.Message.agent_run_id == models.AgentRun.id
            )
            .where(models.Message.id.in_(message_ids))
        )
        with self._session() as s:
            return {
                mid: (run_id, status) for mid, run_id, status in s.execute(stmt).all()
            }

    def count_user_turns_since(self, user_id: str, iso_cutoff: str) -> int:
        """Count user-role messages for *user_id* at or after *iso_cutoff* (ISO-8601 strings sort chronologically, so a ``>=`` compare is a correct cutoff)."""
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
