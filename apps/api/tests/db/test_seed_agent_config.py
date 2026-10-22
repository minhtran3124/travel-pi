"""Seed agent_config: one NULL row per LLM node, idempotent (Task A.5).

Two families live in this table and they are seeded deliberately differently:

* ``AGENT_CONFIG_NODES`` — the chat graph's nodes, inserted with NULL
  provider/model so ``get_agent_llm`` falls back to the env defaults and the
  dashboard can override them per node.
* ``_RESEARCH_AGENT_MIRRORS`` — the trip-research nodes, inserted WITH a
  concrete provider/model mirrored from a sibling of the right model tier. A
  NULL row there is the failure mode documented in
  ``docs/solutions/agent/new-agent-config-node-seeds-null-model.md``: it looks
  configured, then 403s at the provider boundary.

Both families must survive a repeat ``seed_all`` unchanged.
"""

from app.data.agent_config import AGENT_CONFIG_NODES
from app.db.base import Base
from app.db.engine import get_engine, get_session_factory
from app.db.models import AgentConfig
from app.db.seed import _RESEARCH_AGENT_MIRRORS, seed_all

_RESEARCH_NODES = tuple(name for name, _sibling, _fast in _RESEARCH_AGENT_MIRRORS)


def _seeded_twice(tmp_path) -> list[AgentConfig]:
    url = f"sqlite:///{tmp_path / 'seed_agent_config.db'}"
    engine = get_engine(url)
    Base.metadata.create_all(engine, checkfirst=True)
    factory = get_session_factory(url)

    seed_all(factory)
    seed_all(factory)

    with factory() as session:
        return session.query(AgentConfig).all()


def test_seed_agent_config_is_idempotent(tmp_path):
    rows = _seeded_twice(tmp_path)

    assert len(rows) == len(AGENT_CONFIG_NODES) + len(_RESEARCH_NODES)
    assert {r.agent_name for r in rows} == set(AGENT_CONFIG_NODES) | set(
        _RESEARCH_NODES
    )


def test_chat_nodes_are_seeded_null(tmp_path):
    rows = [r for r in _seeded_twice(tmp_path) if r.agent_name in AGENT_CONFIG_NODES]

    assert len(rows) == len(AGENT_CONFIG_NODES)
    assert all(
        r.provider is None and r.model is None and r.base_url is None for r in rows
    )


def test_research_nodes_are_seeded_with_a_concrete_model(tmp_path):
    rows = [r for r in _seeded_twice(tmp_path) if r.agent_name in _RESEARCH_NODES]

    assert len(rows) == len(_RESEARCH_NODES)
    assert all(r.provider and r.model for r in rows)
