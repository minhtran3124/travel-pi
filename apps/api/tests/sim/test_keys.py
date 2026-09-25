import time

import jwt
import pytest
from app.core import auth
from app.core.config import Settings
from app.exceptions import AuthError
from cryptography.hazmat.primitives.asymmetric import rsa
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
        supabase_jwt_audience="authenticated",
    )


def _sign_with(
    private_key: rsa.RSAPrivateKey,
    kid: str,
) -> str:
    now = int(time.time())
    return jwt.encode(
        {
            "sub": "sim-abc",
            "aud": "authenticated",
            "iss": "sim",
            "iat": now,
            "exp": now + 3600,
        },
        private_key,
        algorithm="RS256",
        headers={"kid": kid},
    )


def test_verifier_accepts_token_from_key_server(key_server):
    request = _request_with_token(key_server.token_for("abc"))

    user = auth._verify_bearer_token(request, _settings(key_server.url))

    assert user.id == "sim-abc"


def test_verifier_rejects_token_with_unknown_kid(key_server):
    other = KeyServer()
    request = _request_with_token(other.token_for("abc"))

    with pytest.raises(AuthError):
        auth._verify_bearer_token(request, _settings(key_server.url))


def test_verifier_rejects_served_kid_signed_by_wrong_key(key_server):
    wrong_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    token = _sign_with(wrong_key, key_server._kid)
    request = _request_with_token(token)

    with pytest.raises(AuthError):
        auth._verify_bearer_token(request, _settings(key_server.url))
