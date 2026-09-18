"""Application configuration read from environment variables (or a local ``.env``); every value has a dev-safe default."""

from functools import lru_cache
from typing import Literal

from pydantic import AliasChoices, Field, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

from app.core.llm_providers import PROVIDER_NAMES

LogLevel = Literal["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"]
Environment = Literal["development", "production", "test"]


def _validate_provider_profile(value: str | None) -> str | None:
    """Reject a provider that isn't a known profile (``app.core.llm_providers``); ``None`` means "fall back" and passes."""
    if value is not None and value not in PROVIDER_NAMES:
        raise ValueError(
            f"Unknown LLM provider profile: {value!r}. "
            f"Known profiles: {sorted(PROVIDER_NAMES)}."
        )
    return value


class Settings(BaseSettings):
    """Runtime configuration for the Travel Planner Mock API."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # "production" disables the interactive API docs; the ``Literal`` fails startup on a typo instead of silently running in dev.
    environment: Environment = "development"

    app_name: str = "Travel Planner Mock API"
    app_description: str = "Mock backend for flight search and hotel booking."
    app_version: str = "0.1.0"

    host: str = "0.0.0.0"
    port: int = 8000

    # Uppercased by the validator below so ``LOG_LEVEL=debug`` works, while a bad value fails fast instead of crashing in ``dictConfig``.
    log_level: LogLevel = "INFO"

    @field_validator("log_level", mode="before")
    @classmethod
    def _normalize_log_level(cls, value: object) -> object:
        return value.upper() if isinstance(value, str) else value

    @field_validator("environment", mode="before")
    @classmethod
    def _normalize_environment(cls, value: object) -> object:
        return value.strip().lower() if isinstance(value, str) else value

    # SQLite file is the zero-config dev/test default; Docker injects a Postgres URL. The engine is selected from this value.
    database_url: str = "sqlite:///travel.db"

    # Weather is the one feature making a real outbound call; Open-Meteo is free and keyless.
    weather_geocoding_url: str = "https://geocoding-api.open-meteo.com/v1/search"
    weather_forecast_url: str = "https://api.open-meteo.com/v1/forecast"
    weather_timeout_seconds: float = 10.0
    weather_forecast_days: int = 3
    # Same keyless Open-Meteo provider; used for historical climate normals.
    weather_archive_url: str = "https://archive-api.open-meteo.com/v1/archive"
    climate_years: int = 3
    # Same keyless Open-Meteo provider; real-time air-quality forecasts.
    weather_air_quality_url: str = (
        "https://air-quality-api.open-meteo.com/v1/air-quality"
    )
    air_quality_forecast_days: int = 3  # forecast horizon; the API supports 1–7

    # OpenRouteService gives real road distance/duration; free but needs a key. Unset → offline haversine fallback.
    ors_api_key: str | None = None
    ors_base_url: str = "https://api.openrouteservice.org"
    ors_timeout_seconds: float = 10.0

    @property
    def routing_provider_enabled(self) -> bool:
        """True when an OpenRouteService API key is configured."""
        return bool(self.ors_api_key and self.ors_api_key.strip())

    # CORS — wide open by default for local dev.
    cors_origins: list[str] = ["*"]
    cors_methods: list[str] = ["*"]
    cors_headers: list[str] = ["*"]
    cors_allow_credentials: bool = True

    # Informational only — NOT enforced; advertised so agents can self-throttle.
    rate_limit_nominal: int = 1000

    # ENFORCED (unlike rate_limit_nominal): DB-backed fixed-window cap on feedback actions per user.
    feedback_rate_limit_max: int = Field(default=30, gt=0)
    feedback_rate_limit_window_seconds: int = Field(default=60, gt=0)

    # Agent models built via init_chat_model() — switching provider is an env change; no key required (tests use FakeLLM). ``llm_provider`` is a profile name from app.core.llm_providers.
    llm_provider: str = "openai"
    llm_model: str = "gpt-5"
    fast_llm_model: str = "gpt-5-mini"  # cheap model for sub-agents / summarize
    embedding_model: str = "text-embedding-3-small"

    # Per-agent overrides live in the DB ``agent_config`` table, resolved in ``get_agent_llm`` via ``AgentConfigCache``.

    # Catch-all OpenAI-compatible gateway host when the selected profile has no base_url; prefer a first-class profile.
    llm_base_url: str | None = None

    # Optional; only needed for a real model. Gateway profiles fall back to the SDK's key when unset.
    openai_api_key: str | None = None
    anthropic_api_key: str | None = None
    google_api_key: str | None = None
    clinepass_api_key: str | None = None
    claude_api_key: str | None = None

    @field_validator("llm_provider")
    @classmethod
    def _check_llm_provider(cls, v: str) -> str:
        return _validate_provider_profile(v)

    # Langfuse observability — disabled by default so test/CI emit no traces and need no keys.
    langfuse_enabled: bool = False
    langfuse_public_key: str | None = None
    langfuse_secret_key: str | None = None
    langfuse_host: str = "https://cloud.langfuse.com"

    # Agent runtime knobs.
    agent_recursion_limit: int = 25  # LangGraph recursion guard per invocation
    summarize_threshold: int = 20  # compress history once messages exceed this
    agent_free_daily_turn_limit: int = 20
    # How long the DB-backed config cache serves before a read polls the DB (a
    # cheap MAX(updated_at) check). Accepts the old env name AGENT_CONFIG_CACHE_TTL_SECONDS as a fallback.
    agent_config_poll_interval_seconds: int = Field(
        default=5,
        validation_alias=AliasChoices(
            "AGENT_CONFIG_POLL_INTERVAL_SECONDS",
            "AGENT_CONFIG_CACHE_TTL_SECONDS",
        ),
    )
    # Default IANA timezone grounding "today" when the client sends no valid timezone.
    agent_timezone: str = "Asia/Ho_Chi_Minh"

    # Trip-research deep agent (specs/trip-research-deep-agent); off by default so no existing behaviour changes.
    research_enabled: bool = False
    research_timeout_s: int = 600
    research_daily_limit: int = 3
    research_stale_minutes: int = 30

    # Server-rendered /dashboard/* pages are operator tools: Basic auth when user+password are set, else open in dev but 404 in production.
    dashboard_basic_user: str | None = None
    dashboard_basic_password: str | None = None

    # Verify Supabase access tokens (RS256/ES256) against the project JWKS. Disabled by default; URLs derive from the project ref, with explicit overrides for self-hosted.
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
