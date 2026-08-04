"""ASGI request limits applied before FastAPI parses large upload bodies."""


MAX_UPLOAD_BYTES = 256 * 1024 * 1024
MULTIPART_BODY_LIMIT = MAX_UPLOAD_BYTES + 1024 * 1024
LEGACY_BODY_LIMIT = ((MAX_UPLOAD_BYTES + 2) // 3) * 4 + 64 * 1024


class _BodyTooLarge(Exception):
    pass


class UploadBodyLimitMiddleware:
    def __init__(
        self,
        app,
        multipart_limit: int = MULTIPART_BODY_LIMIT,
        legacy_limit: int = LEGACY_BODY_LIMIT,
    ):
        self.app = app
        self.multipart_limit = multipart_limit
        self.legacy_limit = legacy_limit

    def _limit_for(self, scope) -> int | None:
        if scope.get("type") != "http" or scope.get("method") != "POST":
            return None
        path = scope.get("path", "")
        if path.endswith("/files/upload"):
            return self.multipart_limit
        if path.endswith("/files"):
            return self.legacy_limit
        return None

    async def __call__(self, scope, receive, send):
        limit = self._limit_for(scope)
        if limit is None:
            await self.app(scope, receive, send)
            return

        headers = {key.lower(): value for key, value in scope.get("headers", [])}
        content_length = headers.get(b"content-length")
        if content_length is not None:
            try:
                if int(content_length) > limit:
                    await self._send_too_large(send)
                    return
            except ValueError:
                pass

        received = 0
        response_started = False

        async def limited_receive():
            nonlocal received
            message = await receive()
            if message.get("type") == "http.request":
                received += len(message.get("body", b""))
                if received > limit:
                    raise _BodyTooLarge
            return message

        async def tracked_send(message):
            nonlocal response_started
            if message.get("type") == "http.response.start":
                response_started = True
            await send(message)

        try:
            await self.app(scope, limited_receive, tracked_send)
        except _BodyTooLarge:
            if response_started:
                raise
            await self._send_too_large(send)

    @staticmethod
    async def _send_too_large(send):
        body = b'{"detail":"Request body is too large"}'
        await send({
            "type": "http.response.start",
            "status": 413,
            "headers": [
                (b"content-type", b"application/json"),
                (b"content-length", str(len(body)).encode("ascii")),
            ],
        })
        await send({"type": "http.response.body", "body": body})
