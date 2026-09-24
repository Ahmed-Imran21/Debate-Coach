import logging
import time

from collections import defaultdict, deque
from typing import Deque, Dict

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse


logger = logging.getLogger(__name__)


class PerClientRateLimitMiddleware(BaseHTTPMiddleware):
    """
    Caps requests per client per minute.

    This protects the database and the shared API key pool from
    a single client hammering the API. It is a separate concern
    from api/rate_limiter.py, which enforces the providers' own
    published limits across the key pool.

    Two things worth knowing about this implementation:

    1. It returns a JSONResponse rather than raising
       HTTPException. Starlette's exception handling lives
       inside the router stack, below custom middleware, so an
       HTTPException raised here would surface to the client as
       a 500 rather than a 429.

    2. State is in-memory and per-process. Running more than one
       backend instance means each instance enforces its own
       budget. Move to a shared store before scaling out.
    """

    def __init__(
        self,
        app,
        max_requests_per_minute: int = 60,
        trust_forwarded_for: bool = False,
    ):
        super().__init__(app)

        self._max = max_requests_per_minute
        self._trust_forwarded_for = trust_forwarded_for

        self._hits: Dict[str, Deque[float]] = defaultdict(deque)
        self._last_sweep = time.monotonic()

    # ---------------------------------------------------------
    # Client identity
    # ---------------------------------------------------------

    def _client_key(self, request: Request) -> str:

        if self._trust_forwarded_for:

            forwarded = request.headers.get("x-forwarded-for")

            # The last entry, not the first: Cloud Run's front end
            # appends the address it actually received the
            # connection from, while everything before it is
            # whatever the client chose to send.
            if forwarded:
                last = forwarded.rsplit(",", 1)[-1].strip()
                if last:
                    return last

        if request.client is not None:
            return request.client.host

        return "unknown"

    # ---------------------------------------------------------
    # Periodic sweep
    # ---------------------------------------------------------

    def _sweep(self, now: float) -> None:
        """
        Drop buckets that have gone quiet.

        Without this the dictionary grows one entry per client
        address seen since process start and never shrinks.
        """

        if now - self._last_sweep < 60:
            return

        self._last_sweep = now
        window_start = now - 60

        stale = [
            key
            for key, hits in self._hits.items()
            if not hits or hits[-1] < window_start
        ]

        for key in stale:
            del self._hits[key]

    # ---------------------------------------------------------
    # Dispatch
    # ---------------------------------------------------------

    async def dispatch(self, request: Request, call_next):

        # Preflight requests carry no credentials and must not
        # be consumed from the client's budget, or CORS itself
        # starts failing under load.
        if request.method == "OPTIONS":
            return await call_next(request)

        now = time.monotonic()
        window_start = now - 60

        self._sweep(now)

        client_key = self._client_key(request)
        hits = self._hits[client_key]

        while hits and hits[0] < window_start:
            hits.popleft()

        if len(hits) >= self._max:

            retry_after = max(1, int(60 - (now - hits[0])))

            logger.warning(
                "Rate limit exceeded for client %s on %s %s",
                client_key,
                request.method,
                request.url.path,
            )

            return JSONResponse(
                status_code=429,
                content={
                    "detail": (
                        "Too many requests. Try again in "
                        f"{retry_after} seconds."
                    )
                },
                headers={"Retry-After": str(retry_after)},
            )

        hits.append(now)

        return await call_next(request)
