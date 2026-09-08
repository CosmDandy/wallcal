"""Request logging: one JSON line per request, on stdout.

Stdout because that is what a container logs to — `docker logs`, or whatever
log driver the host is configured with. Nothing is written to a file, so the
image keeps its read-only root filesystem and there is nothing to rotate.

JSON because these lines are meant to be counted, not only read: who fetches a
wallpaper, from where, how often, and which link they are on. `docker logs
wallcal | jq -r .ip | sort | uniq -c` is the whole analytics stack.
"""

from __future__ import annotations

import json
import logging
import re
import sys
import time
from typing import Any
from urllib.parse import unquote_plus

from starlette.requests import Request
from starlette.types import ASGIApp

LOGGER = "wallcal.access"

# A query string carries the whole wallpaper, quotes included, and a quote can
# be long. Enough to identify the link, not enough to fill the log with prose.
QUERY_LIMIT = 300

# A coordinate next to an IP address turns one line of `docker logs` into a
# person and a place, and this service holds no personal data anywhere else.
# The image keeps the two decimals it was asked for; the log keeps a town.
COORDINATE = re.compile(r"\b(lat|lon)=([^&]*)")


def _coarse(query: str) -> str:
    """Every coordinate in the query, rounded to one decimal.

    The query arrives raw, so the value has to be decoded before it can be read
    as a number: `lat=+51.5074` carries a literal plus, which is a space by the
    time the handler parses it, and `lat=51%2E5074` hides its own point. Both
    are accepted by the endpoint, so both have to be blunted here. Anything that
    does not parse as a number is not a coordinate, and is left as it was.
    """

    def blunt(hit: re.Match[str]) -> str:
        try:
            return f"{hit[1]}={float(unquote_plus(hit[2])):.1f}"
        except ValueError:
            return hit[0]

    return COORDINATE.sub(blunt, query)


def configure() -> None:
    """Send our own access log to stdout as JSON, one line per record."""
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(logging.Formatter("%(message)s"))
    logger = logging.getLogger(LOGGER)
    logger.handlers = [handler]
    logger.setLevel(logging.INFO)
    logger.propagate = False


def client_ip(request: Request) -> str:
    """The caller's address, taken from the proxy headers when they are trusted.

    uvicorn rewrites `request.client` from `X-Forwarded-For` only for peers
    listed in `--forwarded-allow-ips`, so by the time it reaches here the
    address is either the real peer or one a trusted proxy vouched for. Reading
    the header directly would let anyone claim any address.
    """
    return request.client.host if request.client else "-"


class AccessLog:
    """ASGI middleware writing one line per request, after the response.

    Written against the raw ASGI signature rather than BaseHTTPMiddleware: that
    one wraps the response in a stream, which for a 3 MB PNG means holding it
    twice.
    """

    def __init__(self, app: ASGIApp) -> None:
        self.app = app
        self.log = logging.getLogger(LOGGER)

    async def __call__(self, scope: Any, receive: Any, send: Any) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        request = Request(scope)
        started = time.perf_counter()
        status = 500
        size = 0

        async def wrapped_send(message: Any) -> None:
            nonlocal status, size
            if message["type"] == "http.response.start":
                status = message["status"]
            elif message["type"] == "http.response.body":
                size += len(message.get("body", b""))
            await send(message)

        try:
            await self.app(scope, receive, wrapped_send)
        finally:
            self.log.info(json.dumps(self._record(request, status, size, started)))

    def _record(
        self, request: Request, status: int, size: int, started: float
    ) -> dict[str, object]:
        query = request.url.query
        record: dict[str, object] = {
            "ts": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            "ip": client_ip(request),
            "method": request.method,
            "path": request.url.path,
            "status": status,
            "ms": round((time.perf_counter() - started) * 1000),
            "bytes": size,
        }
        if query:
            record["query"] = _coarse(query)[:QUERY_LIMIT]
        agent = request.headers.get("user-agent")
        if agent:
            record["ua"] = agent[:200]
        return record


__all__ = ["AccessLog", "client_ip", "configure"]
