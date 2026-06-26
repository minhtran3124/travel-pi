"""Every route must expose a stable, unique operationId (== handler name)."""

import pytest
from app.main import create_app
from fastapi.routing import APIRoute


def test_operation_ids_are_handler_names() -> None:
    app = create_app()
    schema = app.openapi()
    handler_names = {
        r.name for r in app.routes if isinstance(r, APIRoute) and r.include_in_schema
    }
    op_ids = [
        op["operationId"]
        for methods in schema["paths"].values()
        for op in methods.values()
    ]
    assert set(op_ids) <= handler_names, f"unpinned ids: {set(op_ids) - handler_names}"
    assert len(op_ids) == len(set(op_ids)), "duplicate operationIds"


def test_duplicate_operation_id_fails_startup() -> None:
    """A duplicated handler name must trip the runtime guard in create_app.

    The guard lives in create_app, after include_router and before return, so a
    duplicate handler name fails app startup — not just CI. We force a real
    collision by temporarily appending a second route to the shared api_router
    that reuses an existing handler's name, then assert create_app() itself
    raises a RuntimeError naming the collision. The injected route is removed
    afterwards so the module-level router is left clean for other tests.
    """
    from app.routers.main import router as api_router

    # Borrow a schema-visible handler name so the collision survives the guard's
    # include_in_schema filter (the guard only protects codegen-visible routes).
    existing_name = next(
        r.name
        for r in api_router.routes
        if isinstance(r, APIRoute) and r.include_in_schema
    )

    def _dupe() -> None: ...

    api_router.add_api_route("/__dupe", _dupe, name=existing_name)
    injected = api_router.routes[-1]
    try:
        with pytest.raises(RuntimeError, match=existing_name):
            create_app()
    finally:
        api_router.routes.remove(injected)

    # Sanity: the router is clean again, so create_app() succeeds.
    create_app()
