"""Every route must expose a stable, unique operationId (== handler name)."""

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
