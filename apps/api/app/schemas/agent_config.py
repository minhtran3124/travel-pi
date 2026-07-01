"""AgentConfig schema — per-agent LLM provider/model/base_url override."""

from app.schemas.base import AppBaseModel


class AgentConfig(AppBaseModel):
    agent_name: str
    provider: str | None = None
    model: str | None = None
    base_url: str | None = None
