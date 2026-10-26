"""AgentConfig schema — per-agent LLM provider/model/base_url + knobs override."""

from app.schemas.base import AppBaseModel


class AgentConfig(AppBaseModel):
    agent_name: str
    provider: str | None = None
    model: str | None = None
    base_url: str | None = None
    temperature: float | None = None
    max_tokens: int | None = None
    effort: str | None = None
