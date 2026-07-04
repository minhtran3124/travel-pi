"""AgentConfig ORM model + schema (specs/min-43-db-agent-config Task A.1)."""

import pytest
from app.db import models
from app.db.base import Base
from app.db.engine import get_session_factory
from app.schemas.agent_config import AgentConfig as AgentConfigSchema


@pytest.fixture
def session(tmp_path):
    """A Session on a fresh, unseeded temp DB (create_all picks up ORM columns)."""
    url = f"sqlite:///{tmp_path / 'agent_config.db'}"
    factory = get_session_factory(url)
    Base.metadata.create_all(bind=factory().get_bind())
    with factory() as s:
        yield s


def test_agent_config_model_tablename_and_index():
    assert models.AgentConfig.__tablename__ == "agent_config"
    indexes = {ix.name: ix for ix in models.AgentConfig.__table__.indexes}
    assert "ix_agent_config_agent_name" in indexes
    assert indexes["ix_agent_config_agent_name"].unique is True


def test_agent_config_model_registered_in_all():
    assert "AgentConfig" in models.__all__


def test_agent_config_schema_round_trips_from_orm_object():
    row = models.AgentConfig(
        agent_name="concierge", provider="openai", model="gpt-4o", base_url=None
    )
    schema = AgentConfigSchema.model_validate(row)
    assert schema.agent_name == "concierge"
    assert schema.provider == "openai"
    assert schema.model == "gpt-4o"
    assert schema.base_url is None


def test_agent_config_enabled_defaults_null_and_roundtrips(session):
    """`enabled` is nullable (NULL = on) and stores an explicit bool."""
    from app.db import models

    row = models.AgentConfig(agent_name="reflection")
    session.add(row)
    session.commit()
    session.refresh(row)
    assert row.enabled is None  # NULL default → treated as enabled downstream

    row.enabled = False
    session.commit()
    session.refresh(row)
    assert row.enabled is False
