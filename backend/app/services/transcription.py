"""
Transcription service.

Design notes (read before changing this file):

- There is exactly ONE Groq API key/account here (settings.groq_api_key).
  Do NOT turn this into a list of keys/accounts rotated in a queue to
  multiply throughput. Groq's Acceptable Use Policy prohibits circumventing
  published rate limits via multiple accounts or coordinated usage across
  organizations, and that applies whether the accounts are free or paid.
  If you need more Groq throughput than one account provides, request a
  higher limit from Groq directly (Developer/Enterprise tiers support
  custom rate limits for real production workloads).

- What this file DOES do to maximize legitimate throughput and
  resilience:
    1. A simple in-process rate limiter that keeps our own request rate
       under Groq's real published free/paid-tier ceiling, so we get
       clean 200s instead of noisy 429s.
    2. Retry with exponential backoff for transient errors.
    3. A genuine fallback chain across DIFFERENT vendors: Groq first,
       then OpenAI's Whisper API, then a self-hosted CPU faster-whisper
       instance as a last resort. Each provider's own limits are
       respected independently — this is normal multi-provider
       architecture, not account multiplication.
"""

import asyncio
import time
from dataclasses import dataclass

import httpx
from groq import Groq
from openai import OpenAI
from tenacity import retry, retry_if_exception_type, stop_after_attempt, wait_exponential

from app.core.config import settings


@dataclass
class TranscriptionResult:
    text: str
    words: list[dict]  # [{"word": str, "start": float, "end": float}, ...]
    provider: str


class RateLimiter:
    """Token-bucket style limiter so we stay comfortably under a provider's
    published requests-per-minute limit instead of hitting 429s."""

    def __init__(self, max_requests_per_minute: int):
        self._interval = 60.0 / max_requests_per_minute
        self._lock = asyncio.Lock()
        self._last_call = 0.0

    async def wait(self) -> None:
        async with self._lock:
            now = time.monotonic()
            elapsed = now - self._last_call
            if elapsed < self._interval:
                await asyncio.sleep(self._interval - elapsed)
            self._last_call = time.monotonic()


# Keep comfortably under Groq's published free-tier ceiling (20 req/min).
# If you're on a paid Developer/Enterprise plan with a documented higher
# limit, raise this to match what Groq's dashboard shows for your account —
# do not raise it by adding more accounts.
_groq_limiter = RateLimiter(max_requests_per_minute=18)
_openai_limiter = RateLimiter(max_requests_per_minute=45)

_groq_client = Groq(api_key=settings.groq_api_key)
_openai_client = OpenAI(api_key=settings.openai_api_key) if settings.openai_api_key else None


class AllProvidersFailedError(Exception):
    pass


@retry(
    reraise=True,
    stop=stop_after_attempt(3),
    wait=wait_exponential(multiplier=1, min=1, max=10),
    retry=retry_if_exception_type(Exception),
)
async def _transcribe_with_groq(audio_bytes: bytes, filename: str) -> TranscriptionResult:
    await _groq_limiter.wait()

    def _call() -> dict:
        return _groq_client.audio.transcriptions.create(
            file=(filename, audio_bytes),
            model=settings.groq_model,
            response_format="verbose_json",
            timestamp_granularities=["word"],
        )

    response = await asyncio.to_thread(_call)
    words = [
        {"word": w["word"], "start": w["start"], "end": w["end"]}
        for w in getattr(response, "words", []) or []
    ]
    return TranscriptionResult(text=response.text, words=words, provider="groq")


@retry(
    reraise=True,
    stop=stop_after_attempt(3),
    wait=wait_exponential(multiplier=1, min=1, max=10),
    retry=retry_if_exception_type(Exception),
)
async def _transcribe_with_openai(audio_bytes: bytes, filename: str) -> TranscriptionResult:
    if _openai_client is None:
        raise RuntimeError("OpenAI fallback not configured (OPENAI_API_KEY unset)")

    await _openai_limiter.wait()

    def _call() -> dict:
        return _openai_client.audio.transcriptions.create(
            file=(filename, audio_bytes),
            model="whisper-1",
            response_format="verbose_json",
            timestamp_granularities=["word"],
        )

    response = await asyncio.to_thread(_call)
    words = [
        {"word": w.word, "start": w.start, "end": w.end}
        for w in getattr(response, "words", []) or []
    ]
    return TranscriptionResult(text=response.text, words=words, provider="openai")


async def _transcribe_with_local_cpu(audio_bytes: bytes, filename: str) -> TranscriptionResult:
    """Last-resort fallback: a self-hosted faster-whisper instance running on
    CPU (e.g. an Oracle Cloud Always Free ARM box). Configure its URL via an
    internal service call; this is a placeholder HTTP client so the fallback
    chain has a real third link. Slower than Groq/OpenAI, but free and fully
    under your control."""
    local_cpu_url = "http://local-whisper-cpu:8080/transcribe"
    async with httpx.AsyncClient(timeout=120.0) as client:
        response = await client.post(
            local_cpu_url,
            files={"file": (filename, audio_bytes)},
        )
        response.raise_for_status()
        data = response.json()
    return TranscriptionResult(text=data["text"], words=data.get("words", []), provider="local_cpu")


async def transcribe(audio_bytes: bytes, filename: str) -> TranscriptionResult:
    """Try Groq first, then OpenAI, then local CPU. Raises
    AllProvidersFailedError only if every provider in the chain fails."""
    errors: list[str] = []

    for name, fn in (
        ("groq", _transcribe_with_groq),
        ("openai", _transcribe_with_openai),
        ("local_cpu", _transcribe_with_local_cpu),
    ):
        try:
            return await fn(audio_bytes, filename)
        except Exception as exc:  # noqa: BLE001 - we want to fall through on any provider error
            errors.append(f"{name}: {exc}")

    raise AllProvidersFailedError("; ".join(errors))
