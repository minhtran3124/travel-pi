"""Meta endpoint: service info."""

from fastapi import APIRouter, Request
from fastapi.routing import APIRoute

from app.routers.tags import Tags
from app.schemas.meta import ServiceInfo

router = APIRouter(tags=[Tags.meta])


def _list_endpoints(request: Request) -> list[str]:
    """Derive sorted, deduplicated ``"METHOD /path"`` strings from the live route table so the list can't drift from the API."""
    seen: set[str] = set()
    out: list[str] = []
    for route in request.app.routes:
        if not isinstance(route, APIRoute) or not route.include_in_schema:
            continue
        for method in route.methods or ():
            if method in {"HEAD", "OPTIONS"}:
                continue
            entry = f"{method} {route.path}"
            if entry in seen:
                continue
            seen.add(entry)
            out.append(entry)
    out.sort()
    return out


@router.get("/", response_model=ServiceInfo, summary="Service info")
def root(request: Request) -> ServiceInfo:
    """Return the service name, docs URL, and available endpoint paths."""
    return ServiceInfo(
        name="Travel Planner Mock API",
        docs="/docs",
        endpoints=_list_endpoints(request),
    )
