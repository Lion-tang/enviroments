import asyncio
import importlib


def test_chunked_multipart_body_is_rejected_before_endpoint_parsing():
    request_limits = importlib.import_module("app.core.request_limits")
    downstream_called = False

    async def downstream(_scope, receive, send):
        nonlocal downstream_called
        downstream_called = True
        while True:
            message = await receive()
            if not message.get("more_body"):
                break
        await send({"type": "http.response.start", "status": 200, "headers": []})
        await send({"type": "http.response.body", "body": b"ok"})

    messages = [
        {"type": "http.request", "body": b"12345", "more_body": True},
        {"type": "http.request", "body": b"67890", "more_body": False},
    ]
    sent = []

    async def receive():
        return messages.pop(0)

    async def send(message):
        sent.append(message)

    middleware = request_limits.UploadBodyLimitMiddleware(
        downstream,
        multipart_limit=8,
        legacy_limit=12,
    )
    asyncio.run(middleware(
        {
            "type": "http",
            "method": "POST",
            "path": "/api/v1/servers/1/files/upload",
            "headers": [],
        },
        receive,
        send,
    ))

    assert downstream_called is True
    assert sent[0]["status"] == 413
