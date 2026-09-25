"""Event bus: transcript, WebSocket fan-out, and static UI over one port."""

import json
import time
from pathlib import Path

from websockets.asyncio.server import serve
from websockets.datastructures import Headers
from websockets.http11 import Response

_CONTENT_TYPES = {
    ".html": "text/html; charset=utf-8",
    ".js": "text/javascript; charset=utf-8",
    ".css": "text/css; charset=utf-8",
    ".json": "application/json",
    ".svg": "image/svg+xml",
}


class Bus:
    def __init__(
        self,
        run_dir,
        static_dir,
        port=8765,
    ):
        self.run_dir = Path(run_dir)
        self.static_dir = Path(static_dir)
        self._port = port
        self.history = []
        self._clients = set()
        self._server = None
        self._transcript = None
        self._start = None

    @property
    def port(self):
        return self._port

    async def start(self):
        self.run_dir.mkdir(parents=True, exist_ok=True)
        self._transcript = (self.run_dir / "transcript.jsonl").open(
            "a",
            encoding="utf-8",
        )
        self._start = time.monotonic()
        self._server = await serve(
            self._handler,
            "localhost",
            self._port,
            process_request=self._process_request,
        )
        self._port = self._server.server.sockets[0].getsockname()[1]

    async def stop(self):
        if self._server is not None:
            self._server.close()
            await self._server.wait_closed()
            self._server = None
        if self._transcript is not None:
            self._transcript.close()
            self._transcript = None

    async def publish(self, event):
        stamped = dict(event)
        stamped["t"] = int((time.monotonic() - self._start) * 1000)
        self.history.append(stamped)
        line = json.dumps(stamped)
        self._transcript.write(line + "\n")
        self._transcript.flush()
        for client in list(self._clients):
            await client.send(line)

    async def _handler(self, connection):
        self._clients.add(connection)
        try:
            for event in list(self.history):
                await connection.send(json.dumps(event))
            await connection.wait_closed()
        finally:
            self._clients.discard(connection)

    def _process_request(self, connection, request):
        if request.headers.get("Upgrade", "").lower() == "websocket":
            return None
        rel = request.path.split("?", 1)[0].lstrip("/") or "index.html"
        target = (self.static_dir / rel).resolve()
        root = self.static_dir.resolve()
        if not target.is_relative_to(root) or not target.is_file():
            return connection.respond(404, "Not Found")
        body = target.read_bytes()
        headers = Headers()
        headers["Content-Type"] = _CONTENT_TYPES.get(
            target.suffix,
            "application/octet-stream",
        )
        headers["Content-Length"] = str(len(body))
        return Response(200, "OK", headers, body)
