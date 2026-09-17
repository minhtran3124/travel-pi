"""Quota guard — daily turn limit for the free tier; a router-level precondition (not part of AgentContext) that runs before the graph is invoked."""

import logging
from datetime import datetime, timezone

from app.core.config import get_settings
from app.enums import Tier
from app.exceptions import QuotaExceededError
from app.repositories.conversation import ConversationRepository

logger = logging.getLogger(__name__)


def check_quota(
    *,
    user_id: str,
    tier: Tier,
    repo: ConversationRepository,
) -> None:
    """Raise ``QuotaExceededError`` (429) when a free user exceeds today's UTC-day turn limit."""
    if tier == Tier.PREMIUM:
        return  # unlimited

    settings = get_settings()
    limit = settings.agent_free_daily_turn_limit

    today_utc = datetime.now(timezone.utc).replace(
        hour=0, minute=0, second=0, microsecond=0
    )
    iso_cutoff = today_utc.isoformat()

    count = repo.count_user_turns_since(user_id, iso_cutoff)
    logger.debug(
        "[quota_service] user_id=%s tier=%s turns_today=%d limit=%d",
        user_id,
        tier,
        count,
        limit,
    )

    if count >= limit:
        raise QuotaExceededError(
            f"Daily limit of {limit} messages reached. "
            "Upgrade to premium for unlimited access."
        )
