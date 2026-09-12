"""Data-access for the append-only feedback event log (specs/user-feedback-v1).

ORM persistence only: rows are inserted and read, never updated or deleted
here. Authorization, rateability and transition policy live in the feedback
service; this tier folds the log into the effective read model (DESIGN §3.3)
and recovers the ``(user_id, client_event_id)`` insert race (DESIGN §5.3).
"""

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from app.db import models
from app.enums import FeedbackAction, FeedbackRating, FeedbackReasonCode
from app.repositories.base import Repo
from app.schemas.feedback import (
    VALUE_TO_RATING,
    EffectiveFeedback,
    FeedbackEventRecord,
)


class FeedbackRepository(Repo):
    """ORM-backed store of ``feedback_events``."""

    def find_by_client_event(
        self, *, user_id: str, client_event_id: str
    ) -> FeedbackEventRecord | None:
        """Return the event stored for this actor's idempotency key, if any.

        :param user_id: The effective actor.
        :param client_event_id: The client-minted key of the logical action.
        :return: The matching event, or ``None``.
        """
        stmt = select(models.FeedbackEvent).where(
            models.FeedbackEvent.user_id == user_id,
            models.FeedbackEvent.client_event_id == client_event_id,
        )
        with self._session() as s:
            row = s.scalars(stmt).first()
            return FeedbackEventRecord.model_validate(row) if row is not None else None

    def append(
        self,
        *,
        user_id: str,
        conversation_id: str,
        assistant_message_id: str,
        agent_run_id: str | None,
        action: FeedbackAction,
        client_event_id: str,
        request_fingerprint: str,
        source: str,
        rating: int | None = None,
        reason_code: str | None = None,
        comment: str | None = None,
        locale: str | None = None,
        supersedes_event_id: str | None = None,
    ) -> tuple[FeedbackEventRecord, bool]:
        """Insert one immutable event and return ``(event, inserted)``.

        On the unique ``(user_id, client_event_id)`` race the insert is rolled
        back to a savepoint (so a shared unit-of-work session stays usable) and
        the winning row is returned with ``inserted=False``; the service
        compares fingerprints to decide between replay and conflict.

        :return: ``(inserted event, True)``, or ``(existing event for the same
            key, False)`` when this call lost the insert race.
        """
        row = models.FeedbackEvent(
            user_id=user_id,
            conversation_id=conversation_id,
            assistant_message_id=assistant_message_id,
            agent_run_id=agent_run_id,
            action=action.value,
            rating=rating,
            reason_code=reason_code,
            comment=comment,
            source=source,
            locale=locale,
            client_event_id=client_event_id,
            request_fingerprint=request_fingerprint,
            supersedes_event_id=supersedes_event_id,
        )
        try:
            with self._session() as s:
                with s.begin_nested():  # savepoint: keep a shared (UoW) session usable
                    s.add(row)
                self._commit(s)
                s.refresh(row)
                return FeedbackEventRecord.model_validate(row), True
        except IntegrityError:
            existing = self.find_by_client_event(
                user_id=user_id, client_event_id=client_event_id
            )
            if existing is not None:
                return existing, False
            raise

    def effective_for(
        self, message_ids: list[str]
    ) -> dict[str, EffectiveFeedback | None]:
        """Fold the log of each message into its effective state (DESIGN §3.3).

        One query for all ids; the fold runs in Python ordered by
        ``(created_at, id)``. Every requested id is present in the result,
        ``None`` when the message has no active rating.

        :param message_ids: Assistant message ids to fold.
        :return: ``{message_id: EffectiveFeedback | None}``.
        """
        result: dict[str, EffectiveFeedback | None] = dict.fromkeys(message_ids)
        if not message_ids:
            return result
        stmt = (
            select(models.FeedbackEvent)
            .where(models.FeedbackEvent.assistant_message_id.in_(message_ids))
            .order_by(
                models.FeedbackEvent.assistant_message_id,
                models.FeedbackEvent.created_at,
                models.FeedbackEvent.id,
            )
        )
        with self._session() as s:
            rows = s.scalars(stmt).all()
        for row in rows:
            result[row.assistant_message_id] = _fold(
                result[row.assistant_message_id], row
            )
        return result


def _fold(
    state: EffectiveFeedback | None, event: models.FeedbackEvent
) -> EffectiveFeedback | None:
    """Apply one event to the running effective state (DESIGN §3.3 rules 2–4)."""
    if event.action == FeedbackAction.SET_RATING.value:
        return EffectiveFeedback(
            rating=VALUE_TO_RATING[event.rating],
            rating_event_id=event.id,
            updated_at=event.created_at,
        )
    if event.action == FeedbackAction.RETRACT_RATING.value:
        return None
    # add_detail enriches only an active negative rating; anything else is stale.
    if state is None or state.rating != VALUE_TO_RATING[FeedbackRating.NOT_HELPFUL]:
        return state
    # Rebuild through validation (not ``model_copy``) so ``reason_code`` is
    # always a ``FeedbackReasonCode`` member, never the raw column string.
    reason_code = (
        _reason_code(event.reason_code)
        if event.reason_code is not None
        else state.reason_code
    )
    return EffectiveFeedback.model_validate(
        {
            **state.model_dump(),
            "reason_code": reason_code,
            "comment_present": state.comment_present or bool(event.comment),
            "updated_at": event.created_at,
        }
    )


def _reason_code(raw: str) -> FeedbackReasonCode:
    """Coerce a stored ``reason_code`` column value to the enum.

    The log is append-only, so a code retired from ``FeedbackReasonCode`` can
    still sit in old rows; it folds to the catch-all ``OTHER`` rather than
    crashing the read model.
    """
    try:
        return FeedbackReasonCode(raw)
    except ValueError:
        return FeedbackReasonCode.OTHER
