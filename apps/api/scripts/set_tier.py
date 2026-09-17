#!/usr/bin/env python3
"""Grant or revoke a user's tier in the users table (the source of truth).

``user_id`` is the Supabase user id (JWT ``sub``). Run as a module from ``apps/api/``::

    python -m scripts.set_tier <supabase-user-id> premium
    python -m scripts.set_tier <supabase-user-id> free
"""

from __future__ import annotations

import argparse

from app.core.config import get_settings
from app.db.engine import get_session_factory
from app.enums import Tier
from app.repositories.user import UserRepository

_TIER_VALUES = sorted(t.value for t in Tier)


def set_tier(user_id: str, tier: str) -> str:
    """Upsert ``user_id`` to ``tier`` and return the stored tier."""
    if tier not in _TIER_VALUES:
        raise ValueError(f"Invalid tier {tier!r}; must be one of {_TIER_VALUES}.")
    factory = get_session_factory(get_settings().database_url)
    repo = UserRepository(factory)
    repo.upsert_tier(user_id, tier)
    return repo.get_tier(user_id)


def main() -> None:
    parser = argparse.ArgumentParser(description="Set a user's tier (free|premium).")
    parser.add_argument("user_id", help="Supabase user id (JWT sub).")
    parser.add_argument("tier", choices=_TIER_VALUES, help="Tier to assign.")
    args = parser.parse_args()
    result = set_tier(args.user_id, args.tier)
    print(f"user {args.user_id!r} -> tier {result!r}")


if __name__ == "__main__":
    main()
