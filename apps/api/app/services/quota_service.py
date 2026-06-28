"""Quota guard — daily turn limit for the free tier (specs/runtime-context-config D4).

This is a router-level precondition, NOT part of AgentContext. It runs before the
graph is invoked. Premium users bypass the check entirely (unlimited). Free users
are counted against today's UTC-day turn budget; hitting the limit raises
``QuotaExceededError`` → HTTP 429.

Counting uses existing data: ``messages`` rows with ``role="user"`` joined to
``conversations.user_id`` via ``conversation_id``. No new table required.
"""

import logging
from datetime import datetime, timezone

from app.core.config import get_settings
from app.exceptions import QuotaExceededError
from app.repositories.conversation import ConversationRepository

logger = logging.getLogger(__name__)


def check_quota(
    *,
    user_id: str,
    tier: str,
    repo: ConversationRepository,
) -> None:
    """Raise ``QuotaExceededError`` (429) when a free user exceeds today's limit.

    :param user_id: The authenticated user's id.
    :param tier: BE-resolved tier string (``"free"`` or ``"premium"``).
    :param repo: A ``ConversationRepository`` bound to the current session.
    """
    if tier == "premium":
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
