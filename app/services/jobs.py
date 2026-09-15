"""
Background execution for session pipelines.

The pipeline runs Silero VAD, a Whisper transcription, and five
LLM calls. On a real speech that is minutes of wall clock, far
longer than any mobile client or load balancer will hold a
request open. So the HTTP handler only enqueues the work and
returns; the client polls GET /v1/sessions/{id} for progress.

This is a thread pool inside the API process, which keeps the
deployment to one container. The pipeline is IO bound almost
end to end (network calls to Groq, disk, ffmpeg subprocess), so
threads are a reasonable fit and the GIL is not the bottleneck.

When you outgrow one box, replace submit() with a real broker
(Celery, RQ, Dramatiq). Nothing outside this module needs to
change, because the rest of the code only ever calls submit().
"""

import logging
import threading

from concurrent.futures import ThreadPoolExecutor
from typing import Callable, Optional
from uuid import UUID


logger = logging.getLogger(__name__)


_executor: Optional[ThreadPoolExecutor] = None
_lock = threading.Lock()
_in_flight: set[UUID] = set()


def start(max_workers: int) -> None:

    global _executor

    if _executor is not None:
        return

    _executor = ThreadPoolExecutor(
        max_workers=max_workers,
        thread_name_prefix="pipeline",
    )


def in_flight_count() -> int:

    with _lock:
        return len(_in_flight)


def is_running(session_id: UUID) -> bool:

    with _lock:
        return session_id in _in_flight


def submit(
    session_id: UUID,
    job: Callable[[], None],
) -> bool:
    """
    Queue a pipeline run.

    Returns False if this session is already being processed,
    which makes the calling endpoint idempotent: a client that
    retries a start request does not launch a second run over
    the same audio.
    """

    if _executor is None:
        raise RuntimeError(
            "Job executor has not been started. This is "
            "called before the FastAPI lifespan handler ran."
        )

    with _lock:

        if session_id in _in_flight:
            return False

        _in_flight.add(session_id)

    def _run() -> None:

        try:
            job()

        except Exception:
            # The pipeline records its own failure against the
            # session row. This is the last-resort log for a
            # failure in the recording itself.
            logger.exception(
                "Pipeline crashed for session %s",
                session_id,
            )

        finally:
            with _lock:
                _in_flight.discard(session_id)

    _executor.submit(_run)

    return True


def shutdown(wait: bool = True) -> None:

    global _executor

    if _executor is None:
        return

    _executor.shutdown(wait=wait)
    _executor = None
