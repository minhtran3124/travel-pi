"""Admin API schemas."""

from app.enums import Tier
from app.schemas.base import AppBaseModel


class SetTierRequest(AppBaseModel):
    """Request body for PATCH /admin/users/{user_id}/tier."""

    tier: Tier


class UserTierResponse(AppBaseModel):
    """Response confirming the persisted tier for a user."""

    user_id: str
    tier: Tier
