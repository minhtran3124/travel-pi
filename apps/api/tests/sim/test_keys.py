import pytest
from app.core import auth
from app.core.config import Settings
from app.exceptions import AuthError
from sim.keys import KeyServer
from starlette.requests import Request


def _request_with_token(token: str) -> Request:
    header = f"Bearer {token}".encode()
    return Request({"type": "http", "headers": [(b"authorization", header)]})


@pytest.fixture
def key_server():
    auth._jwks_clients.clear()
    server = KeyServer()
    server.start()
    try:
        yield server
    finally:
        server.stop()
        auth._jwks_clients.clear()


def _settings(jwks_url: str) -> Settings:
    return Settings(
        supabase_jwks_url=jwks_url,
        supabase_jwt_issuer="sim",
    )


def test_verifier_accepts_token_from_key_server(key_server):
    request = _request_with_token(key_server.token_for("abc"))

    user = auth._verify_bearer_token(request, _settings(key_server.url))

    assert user.id == "sim-abc"


def test_verifier_rejects_token_signed_by_another_key(key_server):
    other = KeyServer()
    request = _request_with_token(other.token_for("abc"))

    with pytest.raises(AuthError):
        auth._verify_bearer_token(request, _settings(key_server.url))
