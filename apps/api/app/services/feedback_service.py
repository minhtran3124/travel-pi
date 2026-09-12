"""Feedback service — authorization, idempotency and transition policy.

Implements DESIGN §5.3 (specs/user-feedback-v1) over the append-only
``feedback_events`` log: resolve the effective actor, fingerprint the accepted
input, replay or ``409`` on the ``(actor, client_event_id)`` key, apply the
single rateable rule, validate the state transition, append.

Privacy: comment bodies never reach ``logger.*`` — only ids and enum values
are logged. This module must not import from ``app.memory`` (pinned by
``tests/architecture/test_feedback_no_memory_edge.py``).
"""

import hashlib
import json
import logging
from collections.abc import Callable
from dataclasses import dataclass

from sqlalchemy.orm import Session

from app.core.auth import AuthUser
from app.core.languages import SUPPORTED_LANGUAGES
from app.enums import FeedbackAction, FeedbackSource
from app.exceptions import (
    AuthError,
    ConflictError,
    DomainValidationError,
    NotFoundError,
)
from app.repositories.conversation import ConversationRepository
from app.repositories.feedback import FeedbackRepository
from app.schemas.feedback import (
    RATING_TO_VALUE,
    VALUE_TO_RATING,
    EffectiveFeedback,
    FeedbackEventRecord,
    FeedbackRequest,
    FeedbackResponse,
)

logger = logging.getLogger(__name__)

#: The one non-enumerating ``404`` message (DESIGN §5.2: never reveal which
#: condition failed — unknown, foreign, user-role and non-completed all match).
NOT_RATEABLE_DETAIL = "Assistant message not found or not rateable."

#: Linked-run status that makes an assistant message rateable.
RATEABLE_RUN_STATUS = "completed"


def _noop_export(event: FeedbackEventRecord) -> None:
    """Export seam — a no-op this round (provider export is deferred, DESIGN §2)."""


#: Best-effort post-commit hook, called with each newly appended event.
export_hook: Callable[[FeedbackEventRecord], None] = _noop_export


@dataclass(frozen=True)
class FeedbackOutcome:
    """What the service decided: the reply body plus the HTTP status to use."""

    response: FeedbackResponse
    status_code: int


def resolve_actor(auth_user: AuthUser | None, anonymous_user_id: str | None) -> str:
    """Effective actor with the agent endpoints' precedence: JWT, else anonymous.

    :raises AuthError: when neither principal is available (``401``).
    """
    if auth_user is not None:
        return auth_user.id
    if anonymous_user_id:
        return anonymous_user_id
    raise AuthError("A valid JWT or an anonymous_user_id is required.")


def fingerprint(body: FeedbackRequest) -> str:
    """sha256 of the canonical accepted input (identity fields excluded)."""
    canonical = json.dumps(
        {
            "action": body.action.value,
            "assistant_message_id": body.assistant_message_id,
            "comment": body.comment,
            "rating": body.rating,
            "reason_code": body.reason_code.value if body.reason_code else None,
        },
        sort_keys=True,
        separators=(",", ":"),
    )
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


class FeedbackService:
    """Owns the feedback write path for one request-scoped session."""

    def __init__(
        self,
        session: Session,
        *,
        schedule: Callable[..., None] | None = None,
    ) -> None:
        """
        :param session: The request-scoped unit-of-work session.
        :param schedule: How to defer the export hook past the commit (e.g.
            ``BackgroundTasks.add_task``); ``None`` runs it inline.
        """
        self._feedback = FeedbackRepository(session)
        self._conversations = ConversationRepository(session)
        self._schedule = schedule

    def submit(
        self,
        body: FeedbackRequest,
        *,
        auth_user: AuthUser | None,
        idempotency_key: str | None = None,
    ) -> FeedbackOutcome:
        """Apply one feedback action (DESIGN §5.3) and return the folded state.

        :param body: The validated request body.
        :param auth_user: The JWT principal, or ``None`` for anonymous callers.
        :param idempotency_key: Optional ``Idempotency-Key`` header; when present
            it must equal ``client_event_id`` (``422`` otherwise).
        :return: The response body and the status code (``201`` new event,
            ``200`` replay or retract no-op).
        """
        client_event_id = str(body.client_event_id)
        if idempotency_key is not None and idempotency_key != client_event_id:
            raise DomainValidationError(
                "Idempotency-Key header must equal client_event_id."
            )
        if body.locale is not None and body.locale not in SUPPORTED_LANGUAGES:
            # DESIGN §3.2: allowlisted short locale. Enum values only — the
            # rejected value is never logged.
            raise DomainValidationError(
                "locale must be one of: " + ", ".join(SUPPORTED_LANGUAGES) + "."
            )
        actor = resolve_actor(auth_user, body.anonymous_user_id)
        fp = fingerprint(body)

        existing = self._feedback.find_by_client_event(
            user_id=actor, client_event_id=client_event_id
        )
        if existing is not None:
            return self._replay_or_conflict(existing, fp)

        target = self._conversations.get_message_for_feedback(body.assistant_message_id)
        if (
            target is None
            or target.owner_user_id != actor
            or target.role != "assistant"
            or target.agent_run_id is None
            or target.run_status != RATEABLE_RUN_STATUS
        ):
            raise NotFoundError(NOT_RATEABLE_DETAIL)

        current = self._feedback.effective_for([target.id])[target.id]
        state_changes = self._check_transition(body.action, current)

        event = self._feedback.append(
            user_id=actor,
            conversation_id=target.conversation_id,
            assistant_message_id=target.id,
            agent_run_id=target.agent_run_id,
            action=body.action,
            client_event_id=client_event_id,
            request_fingerprint=fp,
            source=FeedbackSource.CHAT_MESSAGE_ACTIONS.value,
            rating=RATING_TO_VALUE[body.rating] if body.rating else None,
            reason_code=body.reason_code.value if body.reason_code else None,
            comment=body.comment,
            locale=body.locale,
            supersedes_event_id=current.rating_event_id if current else None,
        )
        if event.request_fingerprint != fp:
            # Lost the same-key insert race to a different payload; the
            # repository returned the winner (an identical winner is a replay
            # in all but name and is answered like our own insert).
            return self._replay_or_conflict(event, fp)

        logger.info(
            "[feedback] %s user=%s message=%s event=%s",
            body.action.value,
            actor,
            target.id,
            event.id,
        )
        self._run_export(event)
        return FeedbackOutcome(
            response=FeedbackResponse(
                feedback_event_id=event.id,
                assistant_message_id=target.id,
                effective_feedback=self._effective(target.id),
            ),
            status_code=201 if state_changes else 200,
        )

    # -- helpers ---------------------------------------------------------------

    def _replay_or_conflict(
        self, existing: FeedbackEventRecord, fp: str
    ) -> FeedbackOutcome:
        if existing.request_fingerprint != fp:
            raise ConflictError(
                "client_event_id was already used with a different request."
            )
        return FeedbackOutcome(
            response=FeedbackResponse(
                feedback_event_id=existing.id,
                assistant_message_id=existing.assistant_message_id,
                effective_feedback=self._effective(existing.assistant_message_id),
                replayed=True,
            ),
            status_code=200,
        )

    @staticmethod
    def _check_transition(
        action: FeedbackAction, current: EffectiveFeedback | None
    ) -> bool:
        """Validate the action against the folded state (DESIGN §3.2 rules).

        :return: Whether the event changes the effective state (``201`` vs the
            documented retract no-op ``200``).
        :raises ConflictError: ``add_detail`` without an active negative rating.
        """
        if action is FeedbackAction.ADD_DETAIL:
            negative = VALUE_TO_RATING[RATING_TO_VALUE["not_helpful"]]
            if current is None or current.rating != negative:
                raise ConflictError(
                    "add_detail requires an active not_helpful rating on this message."
                )
            return True
        if action is FeedbackAction.RETRACT_RATING:
            return current is not None
        return True  # set_rating always replaces

    def _effective(self, message_id: str) -> EffectiveFeedback | None:
        return self._feedback.effective_for([message_id])[message_id]

    def _run_export(self, event: FeedbackEventRecord) -> None:
        if self._schedule is not None:
            self._schedule(export_hook, event)
        else:
            export_hook(event)
