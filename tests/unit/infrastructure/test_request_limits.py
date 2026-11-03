import asyncio

from app.infrastructure.request_limits import RequestBodyLimitMiddleware


def test_incremental_asgi_request_body_limit_returns_413():
    async def run():
        chunks = [b"123456", b"789", b""]
        sent = []
        consumed = []
        async def receive():
            item = chunks.pop(0)
            consumed.append(item)
            return {"type": "http.request", "body": item, "more_body": bool(chunks)}
        async def app(scope, receive, send):
            while (await receive()).get("more_body"):
                pass
            await send({"type": "http.response.start", "status": 200, "headers": []})
            await send({"type": "http.response.body", "body": b"ok"})
        async def send(message): sent.append(message)
        middleware = RequestBodyLimitMiddleware(app, max_bytes=8)
        await middleware({"type": "http", "path": "/api/chat/audio", "headers": []}, receive, send)
        return sent, consumed
    sent, consumed = asyncio.run(run())
    assert sent[0]["status"] == 413
    assert consumed == [b"123456", b"789"]


def test_content_length_is_rejected_before_consuming_request():
    async def run():
        sent = []
        async def receive(): raise AssertionError("body must not be read")
        async def app(*args): raise AssertionError("app must not run")
        async def send(message): sent.append(message)
        middleware = RequestBodyLimitMiddleware(app, max_bytes=8)
        await middleware({"type": "http", "path": "/api/chat/audio", "headers": [(b"content-length", b"9")]}, receive, send)
        return sent
    assert asyncio.run(run())[0]["status"] == 413
