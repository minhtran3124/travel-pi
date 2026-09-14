"""Data-access for agent conversations, messages, and jobs (specs/travel-agent).

ORM persistence only — business logic (graph orchestration) lives in the agent
layer. Returns Pydantic schemas so the ORM stays confined to this tier.
"""

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
        """Return a conversation id that is guaranteed to have a row.

        Get-or-create: when ``conversation_id`` is None a fresh row is created;
        when it is supplied (e.g. a client-minted id, or one restored from the
        browser across reloads) the row is created with that explicit id if it
        does not exist yet. This prevents orphaned messages — a message must
        never reference a conversation that is absent from this table — and
        self-heals ids minted before this guard existed.

        :param conversation_id: The candidate conversation id, or ``None`` to
            always create a fresh conversation.
        :param user_id: The owning user's id.
        :param trip_id: The trip to associate the conversation with, if any.
        :return: A conversation id guaranteed to have a backing row.
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

    def reassign_user(self, *, from_user_id: str, to_user_id: str) -> int:
        """Reassign everything owned by *from_user_id* to *to_user_id*.

        Conversations, ``agent_runs`` and ``feedback_events`` move in the same
        transaction (specs/user-feedback-v1 §3.4) so the new owner sees the
        history together with its runs and feedback. Messages follow
        automatically because they are keyed by ``conversation_id``.

        :param from_user_id: The user id to reassign away from.
        :param to_user_id: The user id to reassign to.
        :return: The number of conversation rows updated.
        """
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
        """Insert one message row.

        :param message_id: Explicit id for the row (e.g. the id already sent to
            the client over SSE); ``None`` mints a UUID.
        :param agent_run_id: The ``agent_runs`` row that produced an assistant
            reply; ``None`` for user turns.
        """
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
        """Load a message with its conversation owner and linked run status.

        One query: messages → conversations on ``conversation_id`` and an outer
        join to ``agent_runs`` on ``agent_run_id`` (string ids, no FK). Whether
        the message is rateable is decided by the feedback service.

        :param message_id: The message id.
        :return: The joined view, or ``None`` when the message does not exist.
        """
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
        """Bulk ``(agent_run_id, run_status)`` per message id — one query.

        Used by the history handler to compute the ``rateable`` flag for a whole
        page without an N+1 (DESIGN §6). Messages with no linked run map to
        ``(None, None)``; a link to a missing run maps to ``(run_id, None)``.

        :param message_ids: The message ids to look up (empty → empty dict).
        :return: ``{message_id: (agent_run_id, run_status)}`` for every id found.
        """
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
        """Count user-role messages for *user_id* on or after *iso_cutoff*.

        Joins messages → conversations on conversation_id so no additional FK is
        needed. ISO-8601 strings sort chronologically, so a ``>=`` string
        comparison yields the correct day-boundary cutoff.

        :param user_id: The owning user's id.
        :param iso_cutoff: ISO-8601 timestamp; only messages at or after this
            cutoff are counted.
        :return: The number of matching user-role messages.
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
