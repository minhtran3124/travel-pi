"""Admin endpoints — specs/agent-identity-tier Task 2.2.

Role-gated routes for administrative operations. Every endpoint requires
a valid Supabase JWT (``get_current_user`` → 401 on missing/invalid token)
and the caller's role must be ``"admin"`` (else 403 via ForbiddenError).
"""

from __future__ import annotations

import logging
from typing import Annotated

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.core.auth import CurrentUserDep
from app.db.session import get_session
from app.exceptions import ForbiddenError
from app.repositories.user import UserRepository
from app.routers.tags import Tags
from app.schemas.admin import SetTierRequest, UserTierResponse
from app.schemas.error import error_responses

logger = logging.getLogger(__name__)

router = APIRouter(
    prefix="/admin",
    tags=[Tags.admin],
    responses=error_responses(401, 403, 422),
)

SessionDep = Annotated[Session, Depends(get_session)]


@router.patch(
    "/users/{user_id}/tier",
    response_model=UserTierResponse,
    summary="Set a user's tier (admin only)",
)
def set_user_tier(
    user_id: str,
    body: SetTierRequest,
    auth_user: CurrentUserDep,
    session: SessionDep,
) -> UserTierResponse:
    """Set the tier for *user_id*.

    Requires a valid JWT whose ``role`` claim equals ``"admin"`` (HTTP 403
    otherwise). The tier value is validated by the request schema (HTTP 422
    for an unknown tier).

    :param user_id: The id of the user whose tier is being changed.
    :param body: The request body carrying the new tier.
    :param auth_user: The authenticated caller (must have the admin role).
    :param session: The request-scoped DB session.
    :return: The updated user id and tier.
    """
    if auth_user.role != "admin":
        raise ForbiddenError("Admin role required.")

    repo = UserRepository(session)
    # Store the raw string value (not the enum) so the String column never sees
    # a "Tier.FREE"-style repr from str(enum).
    repo.upsert_tier(user_id, body.tier.value)
    tier = repo.get_tier(user_id)
    logger.info(
        "[admin] set_user_tier user_id=%s tier=%s by=%s", user_id, tier, auth_user.id
    )
    return UserTierResponse(user_id=user_id, tier=tier)
