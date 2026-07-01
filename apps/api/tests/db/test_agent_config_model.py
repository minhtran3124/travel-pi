"""AgentConfig ORM model + schema (specs/min-43-db-agent-config Task A.1)."""

from app.db import models
from app.schemas.agent_config import AgentConfig as AgentConfigSchema


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
