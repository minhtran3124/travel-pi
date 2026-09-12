"""Feedback schemas (specs/user-feedback-v1 DESIGN §3.3, §5.1).

Request / response shapes for ``POST /agent/feedback`` plus the entity schemas
the repository returns so the ORM stays confined to ``repositories/``. The
wire rating is the string ``helpful`` / ``not_helpful``; the stored value is
``+1`` / ``-1`` (``FeedbackRating``) — the two maps below are the only bridge.
"""

from typing import Literal
from uuid import UUID

from pydantic import Field, field_validator, model_validator

from app.enums import FeedbackAction, FeedbackRating, FeedbackReasonCode
from app.schemas.base import AppBaseModel

RatingLabel = Literal["helpful", "not_helpful"]

#: Wire label -> stored integer.
RATING_TO_VALUE: dict[str, int] = {
    "helpful": FeedbackRating.HELPFUL.value,
    "not_helpful": FeedbackRating.NOT_HELPFUL.value,
}
#: Stored integer -> wire label.
VALUE_TO_RATING: dict[int, str] = {v: k for k, v in RATING_TO_VALUE.items()}

COMMENT_MAX_CHARS = 500


class FeedbackRequest(AppBaseModel):
    """Body of ``POST /agent/feedback`` (DESIGN §5.1).

    Field presence is action-dependent and validated here (a schema ``422``);
    ownership, rateability and state transitions are the service's job.
    """

    client_event_id: UUID = Field(
        description="Stable id per logical UI action; replays reuse it."
    )
    anonymous_user_id: str | None = Field(
        default=None,
        description="Fallback principal when no valid JWT is present; ignored "
        "when authenticated.",
    )
    assistant_message_id: str = Field(
        min_length=1, description="The assistant message being rated."
    )
    action: FeedbackAction
    rating: RatingLabel | None = Field(
        default=None, description="Required for set_rating, forbidden otherwise."
    )
    reason_code: FeedbackReasonCode | None = Field(
        default=None, description="Allowlisted reason; add_detail only."
    )
    comment: str | None = Field(
        default=None,
        description=f"Free text, trimmed, at most {COMMENT_MAX_CHARS} characters; "
        "add_detail only.",
    )
    locale: str | None = Field(
        default=None, max_length=16, description="Advisory short locale, e.g. 'en'."
    )

    @field_validator("comment", mode="before")
    @classmethod
    def _trim_comment(cls, value: object) -> object:
        if isinstance(value, str):
            value = value.strip()
            if not value:
                return None
            if len(value) > COMMENT_MAX_CHARS:
                raise ValueError(f"comment exceeds {COMMENT_MAX_CHARS} characters")
        return value

    @model_validator(mode="after")
    def _fields_match_action(self) -> "FeedbackRequest":
        if self.action is FeedbackAction.SET_RATING:
            if self.rating is None:
                raise ValueError("set_rating requires 'rating'")
            if self.reason_code is not None or self.comment is not None:
                raise ValueError("set_rating does not accept reason_code or comment")
        elif self.action is FeedbackAction.ADD_DETAIL:
            if self.rating is not None:
                raise ValueError("add_detail does not accept 'rating'")
            if self.reason_code is None and self.comment is None:
                raise ValueError("add_detail requires reason_code or comment")
        else:  # RETRACT_RATING
            if (
                self.rating is not None
                or self.reason_code is not None
                or self.comment is not None
            ):
                raise ValueError("retract_rating carries no rating, reason or comment")
        return self


class EffectiveFeedback(AppBaseModel):
    """Folded view of one assistant message's feedback log (DESIGN §3.3)."""

    rating: RatingLabel
    reason_code: FeedbackReasonCode | None = None
    comment_present: bool = False
    rating_event_id: str = Field(description="Id of the active set_rating event.")
    updated_at: str = Field(description="created_at of the last effective event.")


class FeedbackResponse(AppBaseModel):
    """Body of the ``POST /agent/feedback`` reply (DESIGN §5.1)."""

    feedback_event_id: str
    assistant_message_id: str
    effective_feedback: EffectiveFeedback | None = Field(
        default=None, description="Null once the rating is retracted."
    )
    replayed: bool = False


class FeedbackEventRecord(AppBaseModel):
    """One ``feedback_events`` row as the repository returns it (never on the wire)."""

    id: str
    user_id: str
    conversation_id: str
    assistant_message_id: str
    agent_run_id: str | None = None
    action: FeedbackAction
    rating: int | None = None
    reason_code: str | None = None
    comment: str | None = None
    source: str
    locale: str | None = None
    client_event_id: str
    request_fingerprint: str
    supersedes_event_id: str | None = None
    created_at: str


class MessageForFeedback(AppBaseModel):
    """A message joined to its conversation owner and linked run status.

    Returned by ``ConversationRepository.get_message_for_feedback``; the
    rateable decision (role, owner, completed run) is made by the service.
    """

    id: str
    conversation_id: str
    role: str
    agent_run_id: str | None = None
    owner_user_id: str
    run_status: str | None = Field(
        default=None, description="Linked agent_runs.status; None when unlinked."
    )
