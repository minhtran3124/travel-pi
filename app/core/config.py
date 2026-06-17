"""Application configuration.

Settings are read from environment variables (or a local ``.env`` file).
Every value has a sensible default, so the service runs with zero config
for local development. See ``.env.example`` for the available knobs.
"""

from functools import lru_cache
from typing import Literal

from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

LogLevel = Literal["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"]
Environment = Literal["development", "production", "test"]


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

    # Storage — bookings are persisted to this SQLite file (created on first
    # run). Relative paths are resolved from the working directory.
    database_path: str = "travel.db"

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

    @property
    def is_production(self) -> bool:
        """True when running in a production deployment."""
        return self.environment == "production"


@lru_cache
def get_settings() -> Settings:
    """Return the cached application settings instance."""
    return Settings()
