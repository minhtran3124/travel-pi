"""AgentConfigService — validate + persist per-agent LLM config, invalidate cache."""

import math
from dataclasses import dataclass

from sqlalchemy.orm import Session

from app.core.agent_config_cache import AgentConfigCache
from app.core.config import get_settings
from app.core.llm_providers import PROVIDER_NAMES, get_provider
from app.data.agent_config import (  # first app.data import outside seed.py
    AGENT_CONFIG_GROUPS,
    AGENT_CONFIG_NODES,
    AGENT_DESCRIPTIONS,
)
from app.exceptions import DomainValidationError, NotFoundError
from app.repositories.agent_config import AgentConfigRepository

EFFORT_LEVELS: tuple[str, ...] = ("low", "medium", "high", "xhigh", "max")


@dataclass(frozen=True)
class AgentConfigView:
    """Read view for one agent's config (no ORM leak past the service)."""

    agent_name: str
    description: str | None = None
    provider: str | None = None
    model: str | None = None
    temperature: float | None = None
    max_tokens: int | None = None
    effort: str | None = None
    updated_at: str | None = None
    enabled: bool | None = None


@dataclass(frozen=True)
class AgentConfigGroup:
    """A dashboard section: a title, a blurb, and the agents in it."""

    title: str
    blurb: str
    configs: list[AgentConfigView]


def _norm(value: str | None) -> str | None:
    """Empty/whitespace → None; otherwise the stripped string."""
    if value is None:
        return None
    v = value.strip()
    return v or None


def _parse_number(field: str, value: str | None, caster):
    """Parse a numeric form field; blank → None; bad input → DomainValidationError."""
    v = _norm(value)
    if v is None:
        return None
    try:
        return caster(v)
    except ValueError as exc:
        raise DomainValidationError(f"Invalid {field}: {value!r}") from exc


class AgentConfigService:
    """Per-agent LLM config: list/get/update over AgentConfigRepository."""

    def __init__(self, session: Session) -> None:
        self._repo = AgentConfigRepository(session)

    def list_configs(self) -> list[AgentConfigView]:
        """Return one view per node in AGENT_CONFIG_NODES, merged with DB rows."""
        rows = {r.agent_name: r for r in self._repo.list_all()}
        return [self._to_view(rows.get(name), name) for name in AGENT_CONFIG_NODES]

    def list_grouped(self) -> list["AgentConfigGroup"]:
        """Return the configs split into dashboard sections (main / sub / support)."""
        by_name = {v.agent_name: v for v in self.list_configs()}
        return [
            AgentConfigGroup(title, blurb, [by_name[n] for n in names])
            for title, blurb, names in AGENT_CONFIG_GROUPS
        ]

    def get_config(self, agent_name: str) -> AgentConfigView:
        """Return the view for *agent_name*; NotFoundError if not a known node."""
        self._require_known(agent_name)
        return self._to_view(self._repo.get(agent_name), agent_name)

    def update_config(
        self,
        agent_name: str,
        *,
        provider: str,
        model: str,
        temperature: str,
        max_tokens: str,
        enabled: bool | None = None,
        effort: str | None = None,
    ) -> None:
        """Validate + persist config for *agent_name*, then invalidate the cache."""
        self._require_known(agent_name)
        prov = _norm(provider)
        if prov is not None and prov not in PROVIDER_NAMES:
            raise DomainValidationError(f"Unknown provider: {prov!r}")
        temp = _parse_number("temperature", temperature, float)
        if temp is not None and (not math.isfinite(temp) or not 0.0 <= temp <= 2.0):
            raise DomainValidationError(
                f"temperature must be between 0 and 2, got {temp!r}"
            )
        eff_provider = prov or get_settings().llm_provider
        profile = get_provider(eff_provider)
        if (
            temp is not None
            and profile is not None
            and not profile.supports_temperature
        ):
            raise DomainValidationError(
                f"temperature is not supported for provider {eff_provider!r}; leave it blank"
            )
        eff = _norm(effort)
        if eff is not None and eff not in EFFORT_LEVELS:
            raise DomainValidationError(
                f"effort must be one of {', '.join(EFFORT_LEVELS)}, got {eff!r}"
            )
        maxt = _parse_number("max_tokens", max_tokens, int)
        if maxt is not None and maxt < 1:
            raise DomainValidationError(
                f"max_tokens must be a positive integer, got {maxt!r}"
            )
        # None → the caller doesn't own the flag; leave the column untouched.
        extra = {} if enabled is None else {"enabled": enabled}
        self._repo.upsert(
            agent_name,
            provider=prov,
            model=_norm(model),
            base_url=None,  # hidden field — client derives it from the provider profile
            temperature=temp,
            max_tokens=maxt,
            effort=eff,
            **extra,
        )
        AgentConfigCache.invalidate()

    def _require_known(self, agent_name: str) -> None:
        if agent_name not in AGENT_CONFIG_NODES:
            raise NotFoundError(f"Unknown agent: {agent_name!r}")

    @staticmethod
    def _to_view(row, agent_name: str) -> AgentConfigView:
        description = AGENT_DESCRIPTIONS.get(agent_name)
        if row is None:
            return AgentConfigView(agent_name=agent_name, description=description)
        return AgentConfigView(
            agent_name=agent_name,
            description=description,
            provider=row.provider,
            model=row.model,
            temperature=row.temperature,
            max_tokens=row.max_tokens,
            effort=row.effort,
            updated_at=row.updated_at,
            enabled=row.enabled,
        )
