"""ASGI guards for a local, unauthenticated API.

CORS alone does not protect a localhost service: a page that rebinds its own domain
to 127.0.0.1 (DNS rebinding) is same-origin with the API, and browsers do not apply
CORS to WebSockets at all. These guards therefore

* accept only requests whose ``Host`` header names an allowed host (default: the
  loopback names), for HTTP and WebSocket alike;
* refuse WebSocket handshakes whose ``Origin`` is not an allowed CORS origin, the API's
  own origin, or a loopback origin;
* reject request bodies larger than a fixed limit (413) before they are buffered.
"""

from __future__ import annotations

import json
import os
from collections.abc import Iterable
from urllib.parse import urlsplit

LOOPBACK_HOSTS = ("localhost", "127.0.0.1", "::1")
DEFAULT_MAX_BODY_BYTES = 4 * 1024 * 1024


def _hostname(host_header: str) -> str:
    """Hostname of a Host header value without the port ("[::1]:8000" -> "::1")."""
    try:
        return (urlsplit(f"//{host_header}").hostname or "").lower()
    except ValueError:
        return ""


def allowed_hosts_from_env() -> list[str]:
    extra = os.environ.get("FLYMIND_ALLOWED_HOSTS", "")
    return [*LOOPBACK_HOSTS, *(h.strip().lower() for h in extra.split(",") if h.strip())]


def max_body_from_env() -> int:
    try:
        return int(os.environ.get("FLYMIND_MAX_BODY_BYTES", DEFAULT_MAX_BODY_BYTES))
    except ValueError:
        return DEFAULT_MAX_BODY_BYTES


class LocalGuardMiddleware:
    def __init__(
        self,
        app,
        allowed_hosts: Iterable[str],
        allowed_origins: Iterable[str],
        max_body_bytes: int = DEFAULT_MAX_BODY_BYTES,
    ) -> None:
        self.app = app
        self.allowed_hosts = {h.lower().strip("[]") for h in allowed_hosts}
        self.allow_any_host = "*" in self.allowed_hosts
        self.allowed_origins = {o.rstrip("/").lower() for o in allowed_origins}
        self.max_body_bytes = max_body_bytes

    async def __call__(self, scope, receive, send):
        if scope["type"] not in ("http", "websocket"):
            return await self.app(scope, receive, send)
        headers = {k.decode("latin-1").lower(): v.decode("latin-1") for k, v in scope["headers"]}
        host = headers.get("host", "")
        if not self.allow_any_host and _hostname(host) not in self.allowed_hosts:
            return await self._reject(scope, send, 400, "invalid Host header", receive)

        if scope["type"] == "websocket":
            origin = headers.get("origin")
            if origin is not None and not self._origin_ok(origin, host):
                return await self._reject(scope, send, 403, "WebSocket origin not allowed", receive)
            return await self.app(scope, receive, send)

        declared = headers.get("content-length")
        if declared is not None:
            try:
                too_big = int(declared) > self.max_body_bytes
            except ValueError:
                return await self._reject(scope, send, 400, "invalid Content-Length")
            if too_big:
                return await self._reject(scope, send, 413, "request body too large")

        received = 0
        limit = self.max_body_bytes

        async def limited_receive():
            nonlocal received
            message = await receive()
            if message["type"] == "http.request":
                received += len(message.get("body", b""))
                if received > limit:
                    raise _BodyTooLarge
            return message

        response_started = False

        async def tracking_send(message):
            nonlocal response_started
            if message["type"] == "http.response.start":
                response_started = True
            await send(message)

        try:
            await self.app(scope, limited_receive, tracking_send)
        except _BodyTooLarge:
            if not response_started:
                await self._reject(scope, send, 413, "request body too large")

    def _origin_ok(self, origin: str, host: str) -> bool:
        origin = origin.rstrip("/").lower()
        if origin in self.allowed_origins:
            return True
        parts = urlsplit(origin)
        # Same-origin pages (the built web app served by `flymind serve`), and pages served
        # from this machine on any port (dev servers). A remote page cannot carry a loopback
        # origin: under DNS rebinding its origin keeps the attacker's host name.
        return parts.netloc == host.lower() or (parts.hostname or "") in LOOPBACK_HOSTS

    @staticmethod
    async def _reject(scope, send, status: int, detail: str, receive=None) -> None:
        if scope["type"] == "websocket":
            # Closing before accept() makes the server answer the handshake with 403.
            if receive is not None:
                await receive()  # the websocket.connect message
            await send({"type": "websocket.close", "code": 1008, "reason": detail})
            return
        body = json.dumps({"detail": detail}).encode()
        await send(
            {
                "type": "http.response.start",
                "status": status,
                "headers": [
                    (b"content-type", b"application/json"),
                    (b"content-length", str(len(body)).encode()),
                ],
            }
        )
        await send({"type": "http.response.body", "body": body})


class _BodyTooLarge(Exception):
    pass
