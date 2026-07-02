"""AgentConfigRepository — per-agent LLM provider/model/base_url override."""

import logging

from app.core.llm_providers import PROVIDER_NAMES
from app.db import models
from app.exceptions import DomainValidationError
from app.repositories.base import Repo

logger = logging.getLogger(__name__)


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
    ) -> "models.AgentConfig":
        """Insert or update the config row for *agent_name*.

        :param agent_name: The agent name to insert or update.
        :param provider: The LLM provider override, or ``None`` to fall back.
        :param model: The model name override, or ``None`` to fall back.
        :param base_url: The base URL override, or ``None`` to fall back.
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
            self._commit(s)
            s.refresh(row)
            logger.info(
                "[AgentConfigRepository] upsert agent_name=%s provider=%s model=%s",
                agent_name,
                provider,
                model,
            )
            return row
