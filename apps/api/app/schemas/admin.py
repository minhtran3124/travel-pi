"""Admin API schemas — specs/agent-identity-tier Task 2.2."""

from typing import Literal

from app.schemas.base import AppBaseModel


class SetTierRequest(AppBaseModel):
    """Request body for PATCH /admin/users/{user_id}/tier."""

    tier: Literal["free", "premium"]


class UserTierResponse(AppBaseModel):
    """Response confirming the persisted tier for a user."""

    user_id: str
    tier: str
