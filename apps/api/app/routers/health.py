"""Liveness and readiness probes — separate app health from upstream (ORS)."""

from typing import Annotated

from fastapi import APIRouter, Depends

from app.core.config import get_settings
from app.routers.tags import Tags
from app.schemas.base import AppBaseModel
from app.services.booking_service import BookingService, get_booking_service

router = APIRouter(tags=[Tags.health])

BookingsDep = Annotated[BookingService, Depends(get_booking_service)]


class HealthResponse(AppBaseModel):
    status: str


class ReadyResponse(AppBaseModel):
    status: str
    checks: dict[str, str]


@router.get("/healthz", response_model=HealthResponse, summary="Liveness probe")
def healthz() -> HealthResponse:
    """Liveness: the app process is up. Does not touch dependencies."""
    return HealthResponse(status="ok")


@router.get("/readyz", response_model=ReadyResponse, summary="Readiness probe")
def readyz(bookings: BookingsDep) -> ReadyResponse:
    """Readiness: DB must be reachable; routing is a non-fatal upstream (missing ORS key is "fallback", not "not ready")."""
    try:
        database = "ok" if bookings.ping() else "error"
    except Exception:  # DB unreachable — degrade gracefully, don't 500 the probe
        database = "error"
    routing = "live" if get_settings().routing_provider_enabled else "fallback"
    return ReadyResponse(
        status="ready" if database == "ok" else "not_ready",
        checks={"database": database, "routing_provider": routing},
    )
