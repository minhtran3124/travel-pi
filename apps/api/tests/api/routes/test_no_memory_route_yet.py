"""No ``/memory`` HTTP route ships in this delivery (specs/agent-memory-layer-5 Task 0.1).

`ESCALATIONS.md` E001 decision A: PR #214 (the memory-write guard) is still open, so P0#3 —
the ``/memory`` list + hard-delete routes and their settings UI — is deferred to a follow-up
branch. Shipping a delete surface over a store that still accepts poisoned writes would invert
the intended order: the guard stops *new* poison, and this spec's delete path removes poison
already stored.

`app.memory.store` does gain ``list_memory`` / ``delete_memory`` in this delivery, but nothing
a user can reach calls them. This test is what keeps that true — it is an anti-regression pin
on a *deliberate* deferral, not a permanent rule.

**Delete this file** in the first task of the follow-up plan that unfences `PLAN.md` §6
(Tasks D.1–D.3). A failure here means either that work started without lifting the deferral, or
that a ``/memory`` route was added by accident.
"""

from fastapi.testclient import TestClient


def test_openapi_exposes_no_memory_path(client: TestClient):
    """The OpenAPI document must not advertise any ``/memory`` path yet."""
    spec = client.get("/openapi.json")
    assert spec.status_code == 200

    memory_paths = [
        path
        for path in spec.json()["paths"]
        if path == "/memory" or path.startswith("/memory/")
    ]
    assert memory_paths == [], (
        "A /memory route is registered while specs/agent-memory-layer-5 "
        "ESCALATIONS.md E001 still defers P0#3 (PR #214 not merged). Either lift "
        f"the deferral per PLAN.md section 6 and delete this test, or drop: {memory_paths}"
    )


def test_store_management_helpers_are_not_wired_to_any_router():
    """``list_memory`` / ``delete_memory`` exist but no router imports them.

    The route-level check above cannot see a helper reached through some other
    surface, so pin the import edge directly: nothing under ``app.routers``
    references the management helpers while the deferral stands.
    """
    import pkgutil

    import app.routers as routers_pkg

    offenders: list[str] = []
    for mod in pkgutil.iter_modules(routers_pkg.__path__):
        source = (
            __import__("pathlib")
            .Path(routers_pkg.__path__[0], f"{mod.name}.py")
            .read_text(encoding="utf-8")
        )
        if "list_memory" in source or "delete_memory" in source:
            offenders.append(mod.name)

    assert offenders == [], (
        "app.routers must not reference list_memory/delete_memory while "
        f"ESCALATIONS.md E001 defers P0#3; found in: {offenders}"
    )
