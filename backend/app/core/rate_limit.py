import time
from collections import defaultdict

from fastapi import HTTPException, Request, status
from starlette.middleware.base import BaseHTTPMiddleware


class PerClientRateLimitMiddleware(BaseHTTPMiddleware):
    """Caps requests per client IP per minute. This protects your Groq/OpenAI
    spend and your database from a single account (or attacker) hammering
    the API — separate concern from the transcription-provider rate limiter
    in services/transcription.py.

    NOTE: in-memory and per-process, fine for a single instance. Move to a
    shared store (e.g. Redis) once you run more than one backend instance.
    """

    def __init__(self, app, max_requests_per_minute: int = 60):
        super().__init__(app)
        self._max = max_requests_per_minute
        self._hits: dict[str, list[float]] = defaultdict(list)

    async def dispatch(self, request: Request, call_next):
        client_key = request.client.host if request.client else "unknown"
        now = time.monotonic()
        window_start = now - 60

        hits = self._hits[client_key]
        while hits and hits[0] < window_start:
            hits.pop(0)

        if len(hits) >= self._max:
            raise HTTPException(status_code=status.HTTP_429_TOO_MANY_REQUESTS, detail="Rate limit exceeded")

        hits.append(now)
        return await call_next(request)
