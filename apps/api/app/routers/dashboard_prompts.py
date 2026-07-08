"""Server-rendered read-only dashboard pages for browsing prompt versions.

Separate from ``dashboard.py`` (which covers the domain-data pages) since this
group is scoped to ``app.prompts.registry`` — a file-backed, versioned prompt
store, not a DB-backed repository. Same idiom: Jinja2 templates, excluded from
the OpenAPI schema.

Pages:
    GET /dashboard/prompts                    list every known prompt name
    GET /dashboard/prompts/{name}              view one version of a prompt
    GET /dashboard/prompts/{name}/diff         side-by-side diff of two versions
"""

from pathlib import Path

from fastapi import APIRouter, Query, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates

from app.core.prompt_diff import build_line_diff
from app.exceptions import NotFoundError
from app.prompts.registry import registry
from app.routers.tags import Tags

router = APIRouter(prefix="/dashboard", tags=[Tags.dashboard], include_in_schema=False)

# Templates live in app/templates/ — resolve the path relative to this file
# so it works regardless of the current working directory.
_TEMPLATES = Jinja2Templates(directory=str(Path(__file__).parent.parent / "templates"))


def _parse_version(raw: str) -> int:
    """Parse a version string like ``"3"`` or ``"v3"`` into an int.

    :param raw: The raw version string from a query param.
    :raises ValueError: If ``raw`` isn't a valid version number.
    """
    return int(raw[1:] if raw.startswith("v") else raw)


@router.get("/prompts", response_class=HTMLResponse, include_in_schema=False)
async def list_prompts(request: Request) -> HTMLResponse:
    """List every known prompt name with its active version and version count."""
    prompts = [
        {
            "name": name,
            "active": registry.active_version(name),
            "count": len(registry.versions(name)),
        }
        for name in sorted(registry.names())
    ]
    return _TEMPLATES.TemplateResponse(
        request=request,
        name="prompt_list.html",
        context={"request": request, "prompts": prompts},
    )


@router.get("/prompts/{name}", response_class=HTMLResponse, include_in_schema=False)
async def prompt_detail(
    request: Request, name: str, version: str | None = None
) -> HTMLResponse:
    """Show one version of a prompt (defaults to the active version)."""
    try:
        versions = registry.versions(name)
        active = registry.active_version(name)
    except KeyError as e:
        raise NotFoundError(str(e)) from e

    if version is None:
        selected = active
    else:
        try:
            selected = _parse_version(version)
        except ValueError as e:
            raise NotFoundError(f"Invalid version: {version!r}") from e
        if selected not in versions:
            raise NotFoundError(f"Prompt {name!r} has no version v{selected}")

    content = registry.get(name, selected)
    return _TEMPLATES.TemplateResponse(
        request=request,
        name="prompt_detail.html",
        context={
            "request": request,
            "name": name,
            "versions": versions,
            "active": active,
            "selected": selected,
            "content": content,
        },
    )


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
            "name": name,
            "from_v": from_int,
            "to_v": to_int,
            "diff": build_line_diff(old_content, new_content),
        },
    )
