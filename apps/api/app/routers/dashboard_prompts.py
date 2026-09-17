"""Server-rendered read-only Jinja2 pages for browsing versioned prompts, excluded from OpenAPI."""

from pathlib import Path

from fastapi import APIRouter, Depends, Query, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates

from app.core.dashboard_auth import require_dashboard_access
from app.core.prompt_diff import build_line_diff
from app.exceptions import NotFoundError
from app.prompts.registry import registry
from app.routers.tags import Tags

router = APIRouter(
    prefix="/dashboard",
    tags=[Tags.dashboard],
    include_in_schema=False,
    dependencies=[Depends(require_dashboard_access)],
)

# Path relative to this file so it works regardless of the current working directory.
_TEMPLATES = Jinja2Templates(directory=str(Path(__file__).parent.parent / "templates"))


def _parse_version(raw: str) -> int:
    """Parse a version string like ``"3"`` or ``"v3"`` into an int."""
    return int(raw[1:] if raw.startswith("v") else raw)


def _names_meta() -> list[dict]:
    """Every prompt name + its active version, for the sidebar rail."""
    return [
        {"name": name, "active": registry.active_version(name)}
        for name in sorted(registry.names())
    ]


def _render_detail(request: Request, name: str, version: str | None) -> HTMLResponse:
    """Render the browse workspace (sidebar + one prompt version), defaulting to latest."""
    try:
        versions = registry.versions(name)
        active = registry.active_version(name)
    except KeyError as e:
        raise NotFoundError(str(e)) from e

    latest = max(versions)
    if version is None:
        selected = latest
    else:
        try:
            selected = _parse_version(version)
        except ValueError as e:
            raise NotFoundError(f"Invalid version: {version!r}") from e
        if selected not in versions:
            raise NotFoundError(f"Prompt {name!r} has no version v{selected}")

    return _TEMPLATES.TemplateResponse(
        request=request,
        name="prompt_detail.html",
        context={
            "request": request,
            "names_meta": _names_meta(),
            "name": name,
            "versions": versions,
            "active": active,
            "selected": selected,
            "content": registry.get(name, selected),
            "cmp_from": versions[-2] if len(versions) >= 2 else versions[0],
            "cmp_to": latest,
        },
    )


@router.get("/prompts", response_class=HTMLResponse, include_in_schema=False)
async def list_prompts(request: Request) -> HTMLResponse:
    """Browse prompts: sidebar of every name + the first prompt's latest version."""
    names = sorted(registry.names())
    if not names:
        return _TEMPLATES.TemplateResponse(
            request=request,
            name="prompt_detail.html",
            context={
                "request": request,
                "names_meta": [],
                "name": None,
                "versions": [],
                "active": None,
                "selected": None,
                "content": "",
                "cmp_from": None,
                "cmp_to": None,
            },
        )
    return _render_detail(request, names[0], None)


@router.get("/prompts/{name}", response_class=HTMLResponse, include_in_schema=False)
async def prompt_detail(
    request: Request, name: str, version: str | None = None
) -> HTMLResponse:
    """Show one version of a prompt (defaults to the latest version)."""
    return _render_detail(request, name, version)


@router.get(
    "/prompts/{name}/diff", response_class=HTMLResponse, include_in_schema=False
)
async def prompt_diff(
    request: Request,
    name: str,
    from_v: str = Query(alias="from"),
    to_v: str = Query(alias="to"),
) -> HTMLResponse:
    """Show a side-by-side line diff between two versions of a prompt."""
    try:
        from_int = _parse_version(from_v)
        to_int = _parse_version(to_v)
    except ValueError as e:
        raise NotFoundError(f"Invalid version in diff request: {e}") from e

    try:
        old_content = registry.get(name, from_int)
        new_content = registry.get(name, to_int)
    except KeyError as e:
        raise NotFoundError(str(e)) from e

    return _TEMPLATES.TemplateResponse(
        request=request,
        name="prompt_diff.html",
        context={
            "request": request,
            "names_meta": _names_meta(),
            "name": name,
            "from_v": from_int,
            "to_v": to_int,
            "diff": build_line_diff(old_content, new_content),
        },
    )
