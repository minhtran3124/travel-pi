"""Data-access for the append-only feedback event log; authorization and policy live in the feedback service. This tier folds the log into the effective read model and recovers the ``(user_id, client_event_id)`` insert race."""

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
        """Return the event stored for this actor's idempotency key, if any."""
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
        """Insert one immutable event and return ``(event, inserted)``; on the unique ``(user_id, client_event_id)`` race, roll back to a savepoint and return the winner with ``inserted=False``."""
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
        """Fold each message's log into its effective state in one query; every requested id is present, ``None`` when it has no active rating."""
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
    """Apply one event to the running effective state."""
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
    # Rebuild through validation (not model_copy) so reason_code is always a FeedbackReasonCode, never the raw column string.
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
    """Coerce a stored ``reason_code`` to the enum; a code retired from ``FeedbackReasonCode`` folds to ``OTHER`` rather than crashing the read model."""
    try:
        return FeedbackReasonCode(raw)
    except ValueError:
        return FeedbackReasonCode.OTHER
