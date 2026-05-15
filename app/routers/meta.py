"""Meta endpoint: service info."""

from fastapi import APIRouter, Request
from fastapi.routing import APIRoute

from app.schemas.meta import ServiceInfo

router = APIRouter(tags=["meta"])


def _list_endpoints(request: Request) -> list[str]:
    """Walk the live route table for ``"METHOD /path"`` strings.

    Deriving the list (rather than maintaining it by hand in this file) means
    it can never drift from the actual API — adding a router automatically
    surfaces it here, and dashboard routes are filtered out via
    ``include_in_schema=False``.
    """
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
    """Return the service name, docs URL, and available endpoint paths.

    ``endpoints`` is derived from the live route table at request time so it
    stays in sync with the API automatically.
    """
    return ServiceInfo(
        name="Travel Planner Mock API",
        docs="/docs",
        endpoints=_list_endpoints(request),
    )
