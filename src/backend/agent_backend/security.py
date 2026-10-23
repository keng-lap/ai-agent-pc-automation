"""Local browser security checks for the Phase 2 API."""

from __future__ import annotations

from starlette.responses import JSONResponse

from .config import Settings

MAX_REQUEST_BYTES = 16 * 1024
STATE_CHANGING_METHODS = frozenset({"POST", "PUT", "PATCH", "DELETE"})


class LocalWebSecurityMiddleware:
    """Reject requests that do not match the approved local API boundary."""

    def __init__(self, app, settings: Settings) -> None:
        self.app = app
        self.allowed_hosts = frozenset(
            {
                f"127.0.0.1:{settings.backend_port}",
                f"localhost:{settings.backend_port}",
                f"[::1]:{settings.backend_port}",
            }
        )
        self.allowed_origins = frozenset(
            {
                f"http://127.0.0.1:{settings.frontend_port}",
                f"http://localhost:{settings.frontend_port}",
            }
        )

    async def __call__(self, scope, receive, send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        headers: dict[bytes, list[bytes]] = {}
        for name, value in scope["headers"]:
            headers.setdefault(name.lower(), []).append(value)

        hosts = headers.get(b"host", [])
        if len(hosts) != 1 or not hosts[0].strip():
            await self._reject(send, 400, "Host not allowed.")
            return
        host = hosts[0].decode("latin-1").strip().lower()
        if host not in self.allowed_hosts:
            await self._reject(send, 400, "Host not allowed.")
            return

        origins = headers.get(b"origin", [])
        if len(origins) > 1:
            await self._reject(send, 403, "Origin not allowed.")
            return
        origin = origins[0].decode("latin-1") if origins else None
        if origin is not None and origin not in self.allowed_origins:
            await self._reject(send, 403, "Origin not allowed.")
            return

        method = scope["method"].upper()
        if method in STATE_CHANGING_METHODS:
            if origin is None:
                await self._reject(send, 403, "Origin not allowed.")
                return
            content_types = headers.get(b"content-type", [])
            if len(content_types) != 1:
                await self._reject(send, 415, "Content-Type must be application/json.")
                return
            media_type = content_types[0].decode("latin-1").split(";", 1)[0].strip().lower()
            if media_type != "application/json":
                await self._reject(send, 415, "Content-Type must be application/json.")
                return

        lengths = headers.get(b"content-length", [])
        if len(lengths) > 1:
            await self._reject(send, 400, "Invalid Content-Length.")
            return
        if lengths:
            try:
                declared_length = int(lengths[0])
            except ValueError:
                await self._reject(send, 400, "Invalid Content-Length.")
                return
            if declared_length < 0:
                await self._reject(send, 400, "Invalid Content-Length.")
                return
            if declared_length > MAX_REQUEST_BYTES:
                await self._reject(send, 413, "Request body too large.")
                return

        body_messages = []
        body_size = 0
        while True:
            message = await receive()
            if message["type"] == "http.disconnect":
                body_messages.append(message)
                break
            body_messages.append(message)
            body_size += len(message.get("body", b""))
            if body_size > MAX_REQUEST_BYTES:
                await self._reject(send, 413, "Request body too large.")
                return
            if not message.get("more_body", False):
                break

        message_index = 0

        async def replay_body() -> dict:
            nonlocal message_index
            if message_index < len(body_messages):
                message = body_messages[message_index]
                message_index += 1
                return message
            return await receive()

        await self.app(scope, replay_body, send)

    @staticmethod
    async def _reject(send, status_code: int, detail: str) -> None:
        response = JSONResponse(status_code=status_code, content={"detail": detail})
        await response(
            {"type": "http", "asgi": {"version": "3.0"}, "method": "POST", "path": "/"},
            _unused_receive,
            send,
        )


async def _unused_receive() -> dict:
    return {"type": "http.disconnect"}
