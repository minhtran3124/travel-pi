"""Local RS256 identity provider for the user-simulation harness.

Generates an in-memory keypair with a fresh ``kid`` per batch and serves its public
key as JWKS so the real ``app.core.auth`` verifier accepts tokens minted by
``token_for``. Tokens are never written to disk.
"""

from __future__ import annotations

import json
import threading
import time
import uuid
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import jwt
from cryptography.hazmat.primitives.asymmetric import rsa
from jwt.algorithms import RSAAlgorithm


class KeyServer:
    def __init__(
        self,
        host: str = "127.0.0.1",
        port: int = 0,
    ) -> None:
        self._host = host
        self._port = port
        self._private_key = rsa.generate_private_key(
            public_exponent=65537,
            key_size=2048,
        )
        self._kid = str(uuid.uuid4())
        self._jwks = self._build_jwks()
        self._server: ThreadingHTTPServer | None = None
        self._thread: threading.Thread | None = None

    def _build_jwks(self) -> bytes:
        jwk = RSAAlgorithm.to_jwk(self._private_key.public_key(), as_dict=True)
        jwk.update(kid=self._kid, use="sig", alg="RS256")
        return json.dumps({"keys": [jwk]}).encode()

    def start(self) -> None:
        jwks = self._jwks

        class Handler(BaseHTTPRequestHandler):
            def do_GET(self) -> None:
                if self.path != "/.well-known/jwks.json":
                    self.send_response(404)
                    self.end_headers()
                    return
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(jwks)))
                self.end_headers()
                self.wfile.write(jwks)

            def log_message(self, *args) -> None:
                pass

        self._server = ThreadingHTTPServer((self._host, self._port), Handler)
        self._port = self._server.server_address[1]
        self._thread = threading.Thread(
            target=self._server.serve_forever,
            daemon=True,
        )
        self._thread.start()

    def stop(self) -> None:
        if self._server is not None:
            self._server.shutdown()
            self._server.server_close()
            self._server = None
        if self._thread is not None:
            self._thread.join(timeout=2.0)
            self._thread = None

    @property
    def url(self) -> str:
        if self._server is None:
            raise RuntimeError("KeyServer.start() has not been called.")
        return f"http://{self._host}:{self._port}/.well-known/jwks.json"

    def token_for(self, persona_id: str) -> str:
        now = int(time.time())
        return jwt.encode(
            {
                "sub": f"sim-{persona_id}",
                "aud": "authenticated",
                "iss": "sim",
                "iat": now,
                "exp": now + 3600,
            },
            self._private_key,
            algorithm="RS256",
            headers={"kid": self._kid},
        )
