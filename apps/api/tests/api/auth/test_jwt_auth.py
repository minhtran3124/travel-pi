"""Unit tests for the Supabase JWKS auth dependency (specs/supabase-auth).

Fully offline: an RSA keypair is generated in-process, tokens are signed with
the private key, and ``app.core.auth._get_jwks_client`` is monkeypatched to hand
back the matching public key — so ``get_current_user`` never touches the real
Supabase JWKS endpoint. Every invalid path must yield a 401 envelope.
"""

from __future__ import annotations

import time

import jwt
import pytest
from app.core import auth
from app.core.auth import AuthUser, CurrentUserDep
from app.core.config import Settings
from app.core.errors import register_exception_handlers
from cryptography.hazmat.primitives.asymmetric import rsa
from fastapi import FastAPI
from fastapi.testclient import TestClient

PROJECT_REF = "testref"
ISSUER = f"https://{PROJECT_REF}.supabase.co/auth/v1"
AUDIENCE = "authenticated"

# One keypair for the whole module (2048-bit gen is the slow part).
_PRIVATE_KEY = rsa.generate_private_key(public_exponent=65537, key_size=2048)
_PUBLIC_KEY = _PRIVATE_KEY.public_key()
_OTHER_PRIVATE_KEY = rsa.generate_private_key(public_exponent=65537, key_size=2048)


def _make_token(
    *,
    sub: str = "user-123",
    email: str = "traveler@example.com",
    role: str = AUDIENCE,
    aud: str = AUDIENCE,
    iss: str = ISSUER,
    expires_in: int = 3600,
    app_metadata: dict | None = None,
    signing_key: rsa.RSAPrivateKey = _PRIVATE_KEY,
) -> str:
    now = int(time.time())
    payload = {
        "sub": sub,
        "email": email,
        "role": role,
        "aud": aud,
        "iss": iss,
        "iat": now,
        "exp": now + expires_in,
    }
    if app_metadata is not None:
        payload["app_metadata"] = app_metadata
    return jwt.encode(payload, signing_key, algorithm="RS256")


class _FakeSigningKey:
    def __init__(self, key: object) -> None:
        self.key = key


class _FakeJWKSClient:
    """Stand-in for PyJWKClient that returns the local public key, no network."""

    def get_signing_key_from_jwt(self, token: str) -> _FakeSigningKey:
        return _FakeSigningKey(_PUBLIC_KEY)


@pytest.fixture
def client(monkeypatch: pytest.MonkeyPatch) -> TestClient:
    settings = Settings(
        supabase_url=None,
        supabase_project_ref=PROJECT_REF,
        supabase_jwt_audience=AUDIENCE,
    )
    monkeypatch.setattr(auth, "get_settings", lambda: settings)
    monkeypatch.setattr(auth, "_get_jwks_client", lambda url: _FakeJWKSClient())

    app = FastAPI()
    register_exception_handlers(app, settings)

    @app.get("/whoami")
    def whoami(user: CurrentUserDep) -> dict:
        return {"id": user.id, "email": user.email, "role": user.role}

    return TestClient(app, raise_server_exceptions=False)


def _auth(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


def test_valid_token_authenticates(client: TestClient) -> None:
    resp = client.get("/whoami", headers=_auth(_make_token()))
    assert resp.status_code == 200
    body = resp.json()
    # role is sourced from app_metadata.role, not the top-level (Postgres) role
    # claim — a standard token without app_metadata yields role=None.
    assert body == {
        "id": "user-123",
        "email": "traveler@example.com",
        "role": None,
    }


def test_app_metadata_role_becomes_authuser_role(client: TestClient) -> None:
    """An admin marked via app_metadata.role is exposed as AuthUser.role."""
    token = _make_token(app_metadata={"role": "admin"})
    resp = client.get("/whoami", headers=_auth(token))
    assert resp.status_code == 200
    assert resp.json()["role"] == "admin"


def test_dependency_returns_authuser_directly() -> None:
    # Sanity: the AuthUser shape the dependency builds.
    user = AuthUser(id="x", email="e@x.com", role="authenticated", claims={})
    assert user.id == "x"


def test_missing_authorization_header_is_401(client: TestClient) -> None:
    resp = client.get("/whoami")
    assert resp.status_code == 401
    assert resp.json()["error"] == "AuthError"


def test_non_bearer_header_is_401(client: TestClient) -> None:
    resp = client.get("/whoami", headers={"Authorization": "Basic abc123"})
    assert resp.status_code == 401


def test_garbage_token_is_401(client: TestClient) -> None:
    resp = client.get("/whoami", headers=_auth("not-a-real-jwt"))
    assert resp.status_code == 401


def test_expired_token_is_401(client: TestClient) -> None:
    resp = client.get("/whoami", headers=_auth(_make_token(expires_in=-10)))
    assert resp.status_code == 401


def test_wrong_audience_is_401(client: TestClient) -> None:
    resp = client.get("/whoami", headers=_auth(_make_token(aud="some-other-aud")))
    assert resp.status_code == 401


def test_wrong_issuer_is_401(client: TestClient) -> None:
    resp = client.get(
        "/whoami", headers=_auth(_make_token(iss="https://evil.example.com"))
    )
    assert resp.status_code == 401


def test_wrong_signing_key_is_401(client: TestClient) -> None:
    forged = _make_token(signing_key=_OTHER_PRIVATE_KEY)
    resp = client.get("/whoami", headers=_auth(forged))
    assert resp.status_code == 401
