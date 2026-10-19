"""Two small guards that sit in front of every route: response headers and body size."""

from __future__ import annotations

import json
import logging
import re

from starlette.types import ASGIApp, Message, Receive, Scope, Send

_SECURITY_HEADERS = [
    (b"x-content-type-options", b"nosniff"),
    (b"referrer-policy", b"no-referrer"),
    (b"x-frame-options", b"DENY"),
]
# An API has nothing to render, so nothing it returns may run as a page. The
# interactive docs need scripts, so this is left off while they are on.
_LOCKDOWN_CSP = (b"content-security-policy", b"default-src 'none'; frame-ancestors 'none'")


class SecurityHeadersMiddleware:
    def __init__(self, app: ASGIApp, *, lock_down: bool) -> None:
        self.app = app
        self.headers = list(_SECURITY_HEADERS) + ([_LOCKDOWN_CSP] if lock_down else [])

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        async def send_with_headers(message: Message) -> None:
            if message["type"] == "http.response.start":
                present = {name.lower() for name, _ in message.get("headers", [])}
                message = dict(message)
                message["headers"] = list(message.get("headers", [])) + [
                    header for header in self.headers if header[0] not in present
                ]
            await send(message)

        await self.app(scope, receive, send_with_headers)


class _BodyTooLarge(Exception):
    pass


class BodyLimitMiddleware:
    """Refuse oversized JSON bodies before they are read into memory.

    Uploads are streamed to disk under their own limit, so the upload route is
    exempt; everything else is small, and a client sending megabytes of "JSON"
    is not a client.
    """

    def __init__(self, app: ASGIApp, *, limit: int, exempt: re.Pattern[str]) -> None:
        self.app = app
        self.limit = limit
        self.exempt = exempt

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http" or self.exempt.search(scope["path"]):
            await self.app(scope, receive, send)
            return

        declared = dict(scope["headers"]).get(b"content-length")
        if declared and declared.isdigit() and int(declared) > self.limit:
            await self._refuse(send)
            return

        received = 0
        started = False

        async def counting_receive() -> Message:
            nonlocal received
            message = await receive()
            if message["type"] == "http.request":
                received += len(message.get("body", b""))
                if received > self.limit:
                    raise _BodyTooLarge
            return message

        async def tracking_send(message: Message) -> None:
            nonlocal started
            if message["type"] == "http.response.start":
                started = True
            await send(message)

        try:
            await self.app(scope, counting_receive, tracking_send)
        except _BodyTooLarge:
            # A chunked body gave no length up front; the answer can still be sent
            # unless the route had already begun replying.
            if not started:
                await self._refuse(send)
            else:
                logging.getLogger("wavelane").warning("oversized body after the reply began")

    @staticmethod
    async def _refuse(send: Send) -> None:
        body = json.dumps({"detail": "request body is too large"}).encode()
        await send(
            {
                "type": "http.response.start",
                "status": 413,
                "headers": [
                    (b"content-type", b"application/json"),
                    (b"content-length", str(len(body)).encode()),
                    (b"connection", b"close"),
                ],
            }
        )
        await send({"type": "http.response.body", "body": body})


class TokenRedactingFilter(logging.Filter):
    """Keep stream tokens out of the access log.

    A player cannot send headers, so its token travels in the URL, and uvicorn
    logs URLs. The token is only good for one track, but it has no business in a
    log file that gets pasted into bug reports.
    """

    _TOKEN = re.compile(r"([?&]token=)[^&\s\"]+")

    def filter(self, record: logging.LogRecord) -> bool:
        if isinstance(record.args, tuple):
            record.args = tuple(
                self._TOKEN.sub(r"\1***", arg) if isinstance(arg, str) else arg
                for arg in record.args
            )
        return True
