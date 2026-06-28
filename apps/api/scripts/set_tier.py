#!/usr/bin/env python3
"""Set a user's tier in the BE users table (specs/agent-identity-tier Task 2.1).

The users table is the source of truth for tier; this is the manual/operational
way to grant or revoke premium. The ``user_id`` is the Supabase user id (the JWT
``sub``) the agent now keys on for authenticated callers.

Run as a module from ``apps/api/`` so ``app`` is importable:

    python -m scripts.set_tier <supabase-user-id> premium
    python -m scripts.set_tier <supabase-user-id> free

Runs against ``settings.database_url`` (so respects DATABASE_URL / .env).
"""

from __future__ import annotations

import argparse

from app.agents.context import TIERS
from app.core.config import get_settings
from app.db.engine import get_session_factory
from app.repositories.user import UserRepository


def set_tier(user_id: str, tier: str) -> str:
    """Upsert ``user_id`` to ``tier`` and return the stored tier."""
    if tier not in TIERS:
        raise ValueError(f"Invalid tier {tier!r}; must be one of {sorted(TIERS)}.")
    factory = get_session_factory(get_settings().database_url)
    repo = UserRepository(factory)
    repo.upsert_tier(user_id, tier)
    return repo.get_tier(user_id)


def main() -> None:
    parser = argparse.ArgumentParser(description="Set a user's tier (free|premium).")
    parser.add_argument("user_id", help="Supabase user id (JWT sub).")
    parser.add_argument("tier", choices=sorted(TIERS), help="Tier to assign.")
    args = parser.parse_args()
    result = set_tier(args.user_id, args.tier)
    print(f"user {args.user_id!r} -> tier {result!r}")


if __name__ == "__main__":
    main()
