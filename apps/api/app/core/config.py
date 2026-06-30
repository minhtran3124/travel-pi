"""Application configuration.

Settings are read from environment variables (or a local ``.env`` file).
Every value has a sensible default, so the service runs with zero config
for local development. See ``.env.example`` for the available knobs.
"""

from functools import lru_cache
from typing import Literal

from pydantic import BaseModel, ConfigDict, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

LogLevel = Literal["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"]
Environment = Literal["development", "production", "test"]
# Provider strings accepted by LangChain's init_chat_model(model_provider=...).
# Note: Google's canonical key is "google_genai" (AI Studio / Gemini API) — a
# bare "google" is rejected by init_chat_model.
LLMProvider = Literal["openai", "anthropic", "google_genai"]


class AgentLLMConfig(BaseModel):
    """Per-agent LLM override (see ``app.clients.llm.get_agent_llm``).

    Lets each graph node run on its own provider/model/knobs. Every field is
    optional: ``provider`` falls back to the global ``llm_provider`` and
    ``model`` to the node's tier default (fast vs main). Any extra key (e.g.
    ``max_tokens``) passes straight through to the chat model.
    """

    model_config = ConfigDict(extra="allow", protected_namespaces=())

    provider: LLMProvider | None = None
    model: str | None = None
    temperature: float | None = None


class Settings(BaseSettings):
    """Runtime configuration for the Travel Planner Mock API."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # Deployment environment. When set to "production" the interactive API
    # docs (/docs, /redoc, /openapi.json) are disabled — a FastAPI best
    # practice so the schema is not exposed in production. Local dev and the
    # test suite leave it at "development", where the docs stay on. A typo
    # like ``ENVIRONMENT=producton`` used to silently run in dev — the
    # ``Literal`` constrains it so a bad value fails startup with a clear
    # error naming the offending field.
    environment: Environment = "development"

    # OpenAPI / app metadata.
    app_name: str = "Travel Planner Mock API"
    app_description: str = "Mock backend for flight search and hotel booking."
    app_version: str = "0.1.0"

    # Server.
    host: str = "0.0.0.0"
    port: int = 8000

    # Logging — the minimum level emitted to the console. Applied
    # process-wide by ``app.core.logging``. The validator below uppercases
    # the input so ``LOG_LEVEL=debug`` (the common form people type) still
    # works, while ``LOG_LEVEL=debugg`` fails fast with a clear error
    # instead of crashing later inside ``dictConfig``.
    log_level: LogLevel = "INFO"

    @field_validator("log_level", mode="before")
    @classmethod
    def _normalize_log_level(cls, value: object) -> object:
        return value.upper() if isinstance(value, str) else value

    @field_validator("environment", mode="before")
    @classmethod
    def _normalize_environment(cls, value: object) -> object:
        return value.strip().lower() if isinstance(value, str) else value

    # Storage — SQLAlchemy connection URL. SQLite (a file) is the zero-config
    # default for local dev and the test suite; Docker injects a Postgres URL
    # (e.g. postgresql+psycopg://travel:travel@db:5432/travel). The engine is
    # selected entirely from this value — see app/db/engine.py.
    database_url: str = "sqlite:///travel.db"

    # Weather — the one feature that makes a real outbound call. Open-Meteo is
    # free and needs no API key; these knobs only exist for tuning/testing.
    weather_geocoding_url: str = "https://geocoding-api.open-meteo.com/v1/search"
    weather_forecast_url: str = "https://api.open-meteo.com/v1/forecast"
    weather_timeout_seconds: float = 10.0
    weather_forecast_days: int = 3
    # Same keyless Open-Meteo provider; used for historical climate normals.
    weather_archive_url: str = "https://archive-api.open-meteo.com/v1/archive"
    climate_years: int = 3  # number of years of history to average for climate normals
    # Same keyless Open-Meteo provider; used for real-time air-quality forecasts.
    weather_air_quality_url: str = (
        "https://air-quality-api.open-meteo.com/v1/air-quality"
    )
    air_quality_forecast_days: int = 3  # forecast horizon; the API supports 1–7

    # Routing — /places/route. OpenRouteService gives real road distance and
    # duration per travel mode; it is free but needs an API key (no credit
    # card). Leave ``ors_api_key`` unset and the endpoint still works — it
    # falls back to an offline straight-line (haversine) estimate.
    ors_api_key: str | None = None
    ors_base_url: str = "https://api.openrouteservice.org"
    ors_timeout_seconds: float = 10.0

    @property
    def routing_provider_enabled(self) -> bool:
        """True when an OpenRouteService API key is configured."""
        return bool(self.ors_api_key and self.ors_api_key.strip())

    # CORS — wide open by default so the FE (usually on :3000) and any agent
    # worker can call freely during development.
    cors_origins: list[str] = ["*"]
    cors_methods: list[str] = ["*"]
    cors_headers: list[str] = ["*"]
    cors_allow_credentials: bool = True

    # Informational only — NOT enforced (see CLAUDE.md "no rate limiting").
    # Advertised so agents can self-throttle.
    rate_limit_nominal: int = 1000

    # --- AI / Agent layer (specs/travel-agent) ---
    # Provider-agnostic: the agent layer builds models via init_chat_model(),
    # so switching provider is an env change, not a code change. Every value
    # has a safe default and NO key is required — the suite runs with FakeLLM
    # and never touches the network, so zero-config local dev still works.
    llm_provider: LLMProvider = "openai"
    llm_model: str = "gpt-4.1"
    fast_llm_model: str = "gpt-4.1-mini"  # cheap model for sub-agents / summarize
    embedding_model: str = "text-embedding-3-small"

    # Per-agent LLM overrides — keyed by graph node name (supervisor, planner,
    # concierge, journal, booking, budget, summarize, reflection). Each entry is
    # an AgentLLMConfig; absent nodes use the global provider + tier model. Set
    # via the AGENT_LLM_CONFIGS env var as JSON, e.g.
    #   AGENT_LLM_CONFIGS='{"concierge":{"provider":"anthropic","model":"claude-sonnet-4-6"},"supervisor":{"temperature":0.1}}'
    agent_llm_configs: dict[str, AgentLLMConfig] = {}

    # Optional base URL override — point the LLM client at an OpenAI-compatible
    # gateway/proxy (e.g. clinepass) instead of the provider's default host.
    # Passed straight through to init_chat_model() when set; leave unset to hit
    # the provider directly. Pair it with the matching provider's API key below.
    llm_base_url: str | None = None

    # API keys — optional; only needed when a real model is wired in. Left
    # unset for local dev and CI (tests inject a fake client).
    openai_api_key: str | None = None
    anthropic_api_key: str | None = None
    google_api_key: str | None = None

    # Langfuse observability — disabled by default so test/CI never emit traces
    # or require keys. Enable + set keys in a real deployment.
    langfuse_enabled: bool = False
    langfuse_public_key: str | None = None
    langfuse_secret_key: str | None = None
    langfuse_host: str = "https://cloud.langfuse.com"

    # Agent runtime knobs.
    agent_recursion_limit: int = 25  # LangGraph recursion guard per invocation
    summarize_threshold: int = 20  # compress history once messages exceed this
    agent_free_daily_turn_limit: int = 20  # max user turns per day for the free tier

    # --- Supabase auth (specs/supabase-auth) ---
    # Verify incoming Supabase access tokens (asymmetric RS256/ES256) against
    # the project's JWKS endpoint. Disabled by default so local dev and the test
    # suite need no Supabase project. The JWKS URL and issuer derive from the
    # project ref (or full URL); explicit overrides cover self-hosted setups.
    supabase_url: str | None = None
    supabase_project_ref: str | None = None
    supabase_jwt_audience: str = "authenticated"
    supabase_jwks_url: str | None = None  # explicit override; else derived
    supabase_jwt_issuer: str | None = None  # explicit override; else derived

    @property
    def _supabase_auth_base_url(self) -> str | None:
        """Base Supabase URL (no trailing slash), from full URL or project ref."""
        if self.supabase_url:
            return self.supabase_url.rstrip("/")
        if self.supabase_project_ref:
            return f"https://{self.supabase_project_ref}.supabase.co"
        return None

    @property
    def resolved_jwks_url(self) -> str | None:
        """The JWKS endpoint to verify token signatures against, or None."""
        if self.supabase_jwks_url:
            return self.supabase_jwks_url
        base = self._supabase_auth_base_url
        return f"{base}/auth/v1/.well-known/jwks.json" if base else None

    @property
    def resolved_jwt_issuer(self) -> str | None:
        """The expected ``iss`` claim, or None to skip the issuer check."""
        if self.supabase_jwt_issuer:
            return self.supabase_jwt_issuer
        base = self._supabase_auth_base_url
        return f"{base}/auth/v1" if base else None

    @property
    def is_production(self) -> bool:
        """True when running in a production deployment."""
        return self.environment == "production"

    @model_validator(mode="after")
    def _guard_prod_cors(self) -> "Settings":
        if (
            self.is_production
            and self.cors_allow_credentials
            and "*" in self.cors_origins
        ):
            raise ValueError(
                "Refusing to run in production with cors_allow_credentials=True and a "
                "wildcard origin ('*'): set explicit CORS_ORIGINS."
            )
        return self


@lru_cache
def get_settings() -> Settings:
    """Return the cached application settings instance."""
    return Settings()
