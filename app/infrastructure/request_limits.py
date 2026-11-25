"""Límite ASGI incremental del cuerpo para evitar parsear cargas multipart excesivas."""
import json
from collections.abc import Awaitable, Callable
from typing import Any


class RequestBodyLimitMiddleware:
    def __init__(self, app: Callable[..., Awaitable[None]], *, max_bytes: int):
        self.app = app
        self.max_bytes = max_bytes

    async def __call__(self, scope: dict[str, Any], receive: Callable[..., Awaitable[dict]], send: Callable[..., Awaitable[None]]) -> None:
        if scope["type"] != "http" or scope.get("path") not in {"/api/chat/audio", "/api/admin/chat/audio"}:
            await self.app(scope, receive, send)
            return
        headers = dict(scope.get("headers", ()))
        try:
            if int(headers.get(b"content-length", b"0")) > self.max_bytes:
                await self._reject(send)
                return
        except ValueError:
            await self._reject(send)
            return
        consumed = 0

        class _BodyTooLarge(Exception):
            pass

        async def limited_receive():
            nonlocal consumed
            message = await receive()
            if message.get("type") == "http.request":
                consumed += len(message.get("body", b""))
                if consumed > self.max_bytes:
                    raise _BodyTooLarge
            return message
        try:
            await self.app(scope, limited_receive, send)
        except _BodyTooLarge:
            await self._reject(send)

    @staticmethod
    async def _reject(send):
        body = json.dumps({"detail": "La carga supera el tamaño máximo permitido.", "code": "audio_too_large"}).encode()
        await send({"type": "http.response.start", "status": 413, "headers": [(b"content-type", b"application/json"), (b"content-length", str(len(body)).encode())]})
        await send({"type": "http.response.body", "body": body})
