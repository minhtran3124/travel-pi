"""SC-4: research agent_config rows seeded non-NULL from planner; grader in FAST_AGENTS."""

import pytest
from app.agents.constants import FAST_AGENTS
from app.core.config import get_settings
from app.db import models
from app.db.base import Base
from app.db.engine import get_engine, get_session_factory
from app.db.seed import _seed_agent_config
from sqlalchemy import select


@pytest.fixture
def sf(tmp_path):
    """Empty temp-SQLite session factory (schema only, no rows)."""
    url = f"sqlite:///{tmp_path / 'seed_config.db'}"
    Base.metadata.create_all(get_engine(url))
    return get_session_factory(url)


def _configs(session) -> dict[str, models.AgentConfig]:
    return {r.agent_name: r for r in session.scalars(select(models.AgentConfig))}


def test_grader_in_fast_agents_research_is_not():
    assert "trip_research_grader" in FAST_AGENTS
    assert "trip_research" not in FAST_AGENTS


def test_fresh_db_seeds_research_rows_non_null_by_tier(sf):
    with sf() as session:
        _seed_agent_config(session)
        session.commit()

    with sf() as session:
        rows = _configs(session)

    # Fresh DB: sibling columns are NULL, so each research row copies the global default
    # for its tier — never NULL (the 403 trap), and the fast grader must NOT inherit the
    # slow model (a concrete row value would defeat FAST_AGENTS in get_agent_llm).
    settings = get_settings()
    for name in ("trip_research", "trip_research_grader"):
        assert name in rows
        assert rows[name].provider == settings.llm_provider
        assert rows[name].provider is not None
        assert rows[name].model is not None
    assert rows["trip_research"].model == settings.llm_model  # mirrors planner (slow)
    assert (
        rows["trip_research_grader"].model == settings.fast_llm_model
    )  # summarize (fast)
    if settings.llm_model != settings.fast_llm_model:
        assert rows["trip_research"].model != rows["trip_research_grader"].model


def test_seeds_from_existing_sibling_rows(sf):
    # A DB that already holds configured sibling rows: each research row copies its own
    # sibling verbatim — trip_research←planner, trip_research_grader←summarize (fast).
    gw = "https://api.cline.bot/api/v1"
    with sf() as session:
        session.add(
            models.AgentConfig(
                agent_name="planner",
                provider="clinepass",
                model="openai/gpt-5.4",
                base_url=gw,
            )
        )
        session.add(
            models.AgentConfig(
                agent_name="summarize",
                provider="clinepass",
                model="openai/gpt-5.4-nano",
                base_url=gw,
            )
        )
        session.commit()

    with sf() as session:
        _seed_agent_config(session)
        session.commit()

    with sf() as session:
        rows = _configs(session)

    assert rows["trip_research"].provider == "clinepass"
    assert rows["trip_research"].model == "openai/gpt-5.4"
    assert rows["trip_research"].base_url == gw
    assert rows["trip_research_grader"].provider == "clinepass"
    assert rows["trip_research_grader"].model == "openai/gpt-5.4-nano"
    assert rows["trip_research_grader"].base_url == gw


def test_reseed_is_idempotent(sf):
    with sf() as session:
        _seed_agent_config(session)
        session.commit()
    with sf() as session:
        _seed_agent_config(session)  # second pass must not duplicate or null out
        session.commit()

    with sf() as session:
        for name in ("trip_research", "trip_research_grader"):
            found = session.scalars(
                select(models.AgentConfig).where(models.AgentConfig.agent_name == name)
            ).all()
            assert len(found) == 1
            assert found[0].provider is not None
            assert found[0].model is not None
