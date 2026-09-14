import os

from concurrent.futures import ThreadPoolExecutor, Future
from threading import Lock
from typing import Callable, Dict, Optional


# Number of sessions that can be actively orchestrated at once.
#
# Most of a session's wall-clock time is spent waiting on
# network I/O (LLM calls, possibly sitting in the APIClient's
# waiting queue) rather than local CPU, so this can comfortably
# be set higher than the Whisper/VAD model pool sizes, which
# specifically bound CPU-heavy inference.
PIPELINE_WORKERS = int(os.environ.get("PIPELINE_WORKERS", "16"))


class PipelineExecutor:
    """
    Bounded pool for running whole per-session pipelines.

    Deliberately separate from the Whisper/VAD model pools in
    audio/transcriber.py and audio/audio_analyzer.py: those bound
    CPU-heavy model inference specifically, while this bounds how
    many sessions are being orchestrated end-to-end at all
    (including time spent waiting on LLM network calls or sitting
    in the API waiting queue).
    """

    def __init__(self, max_workers: int = PIPELINE_WORKERS):

        self._executor = ThreadPoolExecutor(
            max_workers=max_workers,
            thread_name_prefix="session-pipeline",
        )

        self._futures: Dict[str, Future] = {}
        self._lock = Lock()

    def submit(
        self,
        session_id: str,
        func: Callable,
        *args,
        **kwargs,
    ) -> bool:
        """
        Submit a pipeline job for a session.

        Returns False without submitting if a job for this
        session is already running — prevents a session from
        being processed twice if a client retries the upload
        request while the first attempt is still running.
        """

        with self._lock:

            existing = self._futures.get(session_id)

            if existing is not None and not existing.done():
                return False

            future = self._executor.submit(
                func,
                *args,
                **kwargs,
            )

            self._futures[session_id] = future

            return True

    def is_active(self, session_id: str) -> bool:
        """
        Return True if a pipeline job for this session is
        currently running.
        """

        with self._lock:

            future = self._futures.get(session_id)

            return future is not None and not future.done()

    def shutdown(self, wait: bool = True) -> None:

        self._executor.shutdown(wait=wait)