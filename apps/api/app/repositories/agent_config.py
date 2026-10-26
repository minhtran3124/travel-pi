"""AgentConfigRepository — per-agent LLM provider/model/base_url override."""

import logging

from sqlalchemy import func

from app.core.llm_providers import PROVIDER_NAMES
from app.db import models
from app.exceptions import DomainValidationError
from app.repositories.base import Repo

logger = logging.getLogger(__name__)

# Sentinel: distinguishes "caller omitted enabled" (leave column as-is) from an explicit None (write NULL).
_UNSET = object()


class AgentConfigRepository(Repo):
    """ORM-backed store for per-agent LLM config overrides."""

    def list_all(self) -> list["models.AgentConfig"]:
        with self._session() as s:
            return list(
                s.query(models.AgentConfig).order_by(models.AgentConfig.agent_name)
            )

    def max_updated_at(self) -> str | None:
        """Return the greatest ``updated_at`` across all rows, or None — a cheap cross-process freshness probe. Ordering stays correct despite isoformat() dropping fractional seconds, since the timezone offset follows and '+'/'-' sort before '.' in ASCII."""
        with self._session() as s:
            return s.query(func.max(models.AgentConfig.updated_at)).scalar()

    def get(self, agent_name: str) -> "models.AgentConfig | None":
        with self._session() as s:
            return (
                s.query(models.AgentConfig)
                .filter(models.AgentConfig.agent_name == agent_name)
                .one_or_none()
            )

    def upsert(
        self,
        agent_name: str,
        *,
        provider: str | None = None,
        model: str | None = None,
        base_url: str | None = None,
        temperature: float | None = None,
        max_tokens: int | None = None,
        enabled: "bool | None" = _UNSET,
        effort: "str | None" = _UNSET,
    ) -> "models.AgentConfig":
        """Insert or update the config row for *agent_name*. Omit ``enabled`` or ``effort`` to leave the column unchanged (only callers that own the field pass it). Raises DomainValidationError for an unknown *provider*."""
        if provider is not None and provider not in PROVIDER_NAMES:
            raise DomainValidationError(f"Unknown provider: {provider!r}")
        with self._session() as s:
            row = (
                s.query(models.AgentConfig)
                .filter(models.AgentConfig.agent_name == agent_name)
                .one_or_none()
            )
            if row is None:
                row = models.AgentConfig(agent_name=agent_name)
                s.add(row)
            row.provider = provider
            row.model = model
            row.base_url = base_url
            row.temperature = temperature
            row.max_tokens = max_tokens
            if enabled is not _UNSET:
                row.enabled = enabled
            if effort is not _UNSET:
                row.effort = effort
            self._commit(s)
            s.refresh(row)
            logger.info(
                "[AgentConfigRepository] upsert agent_name=%s provider=%s model=%s",
                agent_name,
                provider,
                model,
            )
            return row
