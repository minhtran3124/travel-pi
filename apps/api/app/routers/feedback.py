"""``POST /agent/feedback`` — rate a completed assistant reply (specs/user-feedback-v1).

Thin router: the abuse limit runs first (before any session work), then the
:class:`~app.services.feedback_service.FeedbackService` owns identity,
idempotency, rateability and transitions. Statuses per DESIGN §5.2.
"""

from typing import Annotated

from fastapi import APIRouter, BackgroundTasks, Depends, Header, Request, Response
from sqlalchemy.orm import Session

from app.core.auth import AuthUser, OptionalUserDep
from app.core.config import get_settings
from app.core.rate_limit import enforce_rate_limit
from app.db.session import get_session
from app.routers.tags import Tags
from app.schemas.error import ErrorResponse, error_responses
from app.schemas.feedback import FeedbackRequest, FeedbackResponse
from app.services.feedback_service import FeedbackService

router = APIRouter(prefix="/agent", tags=[Tags.agent], responses=error_responses(422))

SessionDep = Annotated[Session, Depends(get_session)]
IdempotencyKeyDep = Annotated[
    str | None,
    Header(
        alias="Idempotency-Key",
        description="Optional mirror of client_event_id; a different value is 422.",
    ),
]


def feedback_subject(
    auth_user: AuthUser | None, anonymous_user_id: str | None
) -> str | None:
    """Rate-limit subject: the JWT id, else the namespaced anonymous id, else None.

    The ``anon:`` namespace keeps a body-supplied id from exhausting an
    authenticated user's counter (DESIGN §5.2). ``None`` skips the limit; the
    service then answers ``401``.
    """
    if auth_user is not None:
        return auth_user.id
    if anonymous_user_id:
        return f"anon:{anonymous_user_id}"
    return None


def feedback_rate_limit(
    request: Request,
    body: FeedbackRequest,
    session: SessionDep,
    auth_user: OptionalUserDep,
) -> None:
    """Dedicated feedback abuse limit — listed before any session-using dependency.

    Uses the primitive's core callable because the subject comes from the
    request body; the policy is read per request so env overrides apply.
    """
    subject = feedback_subject(auth_user, body.anonymous_user_id)
    if subject is None:
        return
    settings = get_settings()
    enforce_rate_limit(
        session,
        name="feedback",
        subject=subject,
        limit=settings.feedback_rate_limit_max,
        window_seconds=settings.feedback_rate_limit_window_seconds,
        request=request,
    )


@router.post(
    "/feedback",
    response_model=FeedbackResponse,
    status_code=201,
    summary="Rate an assistant reply",
    dependencies=[Depends(feedback_rate_limit)],
    responses={
        200: {
            "model": FeedbackResponse,
            "description": "Idempotent replay or retract with nothing active",
        },
        **error_responses(401, 404, 409),
        429: {"model": ErrorResponse, "description": "Feedback rate limit exceeded"},
    },
)
def submit_feedback(
    body: FeedbackRequest,
    response: Response,
    session: SessionDep,
    auth_user: OptionalUserDep,
    background: BackgroundTasks,
    idempotency_key: IdempotencyKeyDep = None,
) -> FeedbackResponse:
    """Append one feedback event and return the folded effective state.

    ``201`` for a new state-changing event; ``200`` for an idempotent replay or
    a retract with nothing active.
    """
    outcome = FeedbackService(session, schedule=background.add_task).submit(
        body, auth_user=auth_user, idempotency_key=idempotency_key
    )
    response.status_code = outcome.status_code
    return outcome.response
