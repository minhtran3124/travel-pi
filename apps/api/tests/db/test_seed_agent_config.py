"""Seed agent_config: one NULL row per LLM node, idempotent (Task A.5)."""

from app.data.agent_config import AGENT_CONFIG_NODES, SEED_DISABLED_AGENTS
from app.db.base import Base
from app.db.engine import get_engine, get_session_factory
from app.db.models import AgentConfig
from app.db.seed import seed_all


def _seeded(tmp_path, name: str):
    url = f"sqlite:///{tmp_path / 'seed_agent_config.db'}"
    Base.metadata.create_all(get_engine(url), checkfirst=True)
    return url, get_session_factory(url)


def test_seed_agent_config_is_idempotent(tmp_path):
    url = f"sqlite:///{tmp_path / 'seed_agent_config.db'}"
    engine = get_engine(url)
    Base.metadata.create_all(engine, checkfirst=True)
    factory = get_session_factory(url)

    seed_all(factory)
    seed_all(factory)

    with factory() as session:
        rows = session.query(AgentConfig).all()
        assert len(rows) == len(AGENT_CONFIG_NODES)
        assert {r.agent_name for r in rows} == set(AGENT_CONFIG_NODES)
        assert all(
            r.provider is None and r.model is None and r.base_url is None for r in rows
        )


def test_prototype_nodes_seed_disabled(tmp_path):
    """`grader` seeds `enabled=False`; everything else seeds NULL (= on).

    The MIN-59 rubric grader must not add a judge LLM call to any environment until
    its trade-off report exists — the intake's "gated off by default until measured".
    """
    _url, factory = _seeded(tmp_path, "disabled")
    seed_all(factory)

    with factory() as session:
        rows = {r.agent_name: r.enabled for r in session.query(AgentConfig).all()}

    assert rows["grader"] is False
    assert {"grader"} == SEED_DISABLED_AGENTS
    for name, enabled in rows.items():
        if name not in SEED_DISABLED_AGENTS:
            assert enabled is None, (
                f"{name} should seed NULL (enabled), got {enabled!r}"
            )


def test_reseeding_never_clobbers_an_operator_toggle(tmp_path):
    """Once someone enables the grader from the dashboard, re-seeding leaves it on."""
    _url, factory = _seeded(tmp_path, "toggle")
    seed_all(factory)

    with factory() as session:
        session.query(AgentConfig).filter_by(agent_name="grader").one().enabled = True
        session.commit()

    seed_all(factory)

    with factory() as session:
        assert session.query(AgentConfig).filter_by(agent_name="grader").one().enabled
