"""AgentConfigRepository — per-agent LLM provider/model/base_url override."""

import logging

from sqlalchemy import func

from app.core.llm_providers import PROVIDER_NAMES
from app.db import models
from app.exceptions import DomainValidationError
from app.repositories.base import Repo

logger = logging.getLogger(__name__)

# Sentinel: distinguishes "caller omitted enabled" (leave the column as-is)
# from an explicit ``None`` (write NULL). Only callers that own the flag pass it.
_UNSET = object()


class AgentConfigRepository(Repo):
    """ORM-backed store for per-agent LLM config overrides."""

    def list_all(self) -> list["models.AgentConfig"]:
        """Return every stored agent config row.

        :return: All ``AgentConfig`` rows.
        """
        with self._session() as s:
            return list(
                s.query(models.AgentConfig).order_by(models.AgentConfig.agent_name)
            )

    def max_updated_at(self) -> str | None:
        """Return the most recent ``updated_at`` across every row, or ``None`` if empty.

        Cheap cross-process freshness probe (GH-106): a single scalar, not a
        full ``list_all()`` reload. ``updated_at`` is an ISO-8601 string
        (``TimestampMixin``), so ``MAX()`` sorts correctly as text on both
        SQLite and Postgres.

        :return: The lexicographically greatest ``updated_at``, or ``None``.
        """
        with self._session() as s:
            return s.query(func.max(models.AgentConfig.updated_at)).scalar()

    def get(self, agent_name: str) -> "models.AgentConfig | None":
        """Return the config row for *agent_name*, or ``None`` if absent.

        :param agent_name: The agent name to look up.
        :return: The matching ``AgentConfig`` row, or ``None``.
        """
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
    ) -> "models.AgentConfig":
        """Insert or update the config row for *agent_name*.

        :param agent_name: The agent name to insert or update.
        :param provider: The LLM provider override, or ``None`` to fall back.
        :param model: The model name override, or ``None`` to fall back.
        :param base_url: The base URL override, or ``None`` to fall back.
        :param temperature: The sampling temperature, or ``None`` for the default.
        :param max_tokens: The max output tokens, or ``None`` for the default.
        :param enabled: Whether the agent step is enabled. Omit it (the default)
            to leave the column unchanged; new rows then take the model default
            (NULL, treated as enabled). Only callers that own the flag pass it.
        :return: The upserted ``AgentConfig`` row.
        :raises DomainValidationError: If *provider* is not a known profile name
            (see ``app.core.llm_providers.PROVIDER_NAMES``).
        """
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
            self._commit(s)
            s.refresh(row)
            logger.info(
                "[AgentConfigRepository] upsert agent_name=%s provider=%s model=%s",
                agent_name,
                provider,
                model,
            )
            return row
