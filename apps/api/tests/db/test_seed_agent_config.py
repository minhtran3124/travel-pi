"""Seed agent_config: one NULL row per LLM node, idempotent (Task A.5)."""

from app.data.agent_config import AGENT_CONFIG_NODES
from app.db.base import Base
from app.db.engine import get_engine, get_session_factory
from app.db.models import AgentConfig
from app.db.seed import seed_all


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
