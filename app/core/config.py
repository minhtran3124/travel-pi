"""Application configuration.

Settings are read from environment variables (or a local ``.env`` file).
Every value has a sensible default, so the service runs with zero config
for local development. See ``.env.example`` for the available knobs.
"""

from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


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
    # test suite leave it at "development", where the docs stay on.
    environment: str = "development"

    # OpenAPI / app metadata.
    app_name: str = "Travel Planner Mock API"
    app_description: str = "Mock backend for flight search and hotel booking."
    app_version: str = "0.1.0"

    # Server.
    host: str = "0.0.0.0"
    port: int = 8000

    # Logging — the minimum level emitted to the console (DEBUG, INFO,
    # WARNING, ERROR). Applied process-wide by ``app.core.logging``.
    log_level: str = "INFO"

    # Storage — bookings are persisted to this SQLite file (created on first
    # run). Relative paths are resolved from the working directory.
    database_path: str = "travel.db"

    # Weather — the one feature that makes a real outbound call. Open-Meteo is
    # free and needs no API key; these knobs only exist for tuning/testing.
    weather_geocoding_url: str = "https://geocoding-api.open-meteo.com/v1/search"
    weather_forecast_url: str = "https://api.open-meteo.com/v1/forecast"
    weather_timeout_seconds: float = 10.0
    weather_forecast_days: int = 3

    # CORS — wide open by default so the FE (usually on :3000) and any agent
    # worker can call freely during development.
    cors_origins: list[str] = ["*"]
    cors_methods: list[str] = ["*"]
    cors_headers: list[str] = ["*"]
    cors_allow_credentials: bool = True

    @property
    def is_production(self) -> bool:
        """True when running in a production deployment."""
        return self.environment.strip().lower() == "production"


@lru_cache
def get_settings() -> Settings:
    """Return the cached application settings instance."""
    return Settings()
