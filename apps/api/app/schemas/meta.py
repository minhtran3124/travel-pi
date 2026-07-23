"""Schemas for the meta (service info) endpoint."""

from app.schemas.base import AppBaseModel


class ServiceInfo(AppBaseModel):
    """Top-level service description returned by ``GET /``."""

    name: str
    docs: str
    endpoints: list[str]
