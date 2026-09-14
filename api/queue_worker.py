from __future__ import annotations

import time

from threading import Thread, Event
from typing import TYPE_CHECKING, Optional

if TYPE_CHECKING:
    from .client import APIClient


class QueueWorker:
    """
    Background worker that continuously attempts to service
    requests sitting in an APIClient's RequestQueue.

    Runs in its own daemon thread. One worker is created per
    APIClient and shares that client's registry, rate limiter,
    scheduler, and request queue.

    Strategy: pull the next queued request, try to acquire
    capacity for it. If that succeeds, execute it and wake up
    whoever is waiting on it. If it fails, put it back at the
    end of the queue and move on — this behaves like round-robin
    across queued requests, so one request stuck waiting on a
    busy model doesn't block others that could be served by a
    different, free key.
    """

    # How long to sleep before retrying when the queue currently
    # has nothing serviceable. Keeps the worker from busy-spinning.
    RETRY_DELAY_SECONDS = 0.5

    # How long to block waiting on an empty queue before checking
    # the stop flag again.
    POLL_TIMEOUT_SECONDS = 1.0

    def __init__(self, api_client: "APIClient"):
        self.api_client = api_client
        self._stop_event = Event()
        self._thread: Optional[Thread] = None

    # -----------------------------------------------------
    # Lifecycle
    # -----------------------------------------------------

    def start(self) -> None:
        """
        Start the background worker thread.
        """

        if self._thread is not None and self._thread.is_alive():
            return

        self._stop_event.clear()

        self._thread = Thread(
            target=self._run,
            name="APIQueueWorker",
            daemon=True,
        )

        self._thread.start()

    def stop(self) -> None:
        """
        Signal the worker to stop and wait for it to exit.
        """

        self._stop_event.set()

        if self._thread is not None:
            self._thread.join(timeout=5.0)

    # -----------------------------------------------------
    # Main loop
    # -----------------------------------------------------

    def _run(self) -> None:

        while not self._stop_event.is_set():

            queued_request = self.api_client.request_queue.get(
                timeout=self.POLL_TIMEOUT_SECONDS
            )

            if queued_request is None:
                continue

            reservation = self.api_client.scheduler.acquire(
                queued_request.request
            )

            if reservation is None:

                # Still no capacity anywhere compatible. Put it
                # back at the end of the line and give the
                # system a brief moment before trying again.
                self.api_client.request_queue.put(
                    queued_request
                )

                time.sleep(self.RETRY_DELAY_SECONDS)
                continue

            api_key = self.api_client.scheduler.get_reserved_key(
                reservation
            )

            response = self.api_client._execute_request(
                request=queued_request.request,
                reservation=reservation,
                api_key=api_key,
                call_kwargs=queued_request.call_kwargs,
            )

            queued_request.response = response
            queued_request.event.set()