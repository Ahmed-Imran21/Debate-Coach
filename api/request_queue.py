from collections import deque
from threading import Condition
from typing import Optional

from .models import APIRequest


class RequestQueue:
    """
    Thread-safe queue for pending API requests.

    Requests are added to the queue when they cannot immediately
    be assigned to an API key.

    The queue is intentionally independent of providers and API keys.
    """

    def __init__(self):
        self._queue = deque()
        self._condition = Condition()

    # ============================================================
    # ADD
    # ============================================================

    def put(self, request: APIRequest) -> None:
        """
        Add a request to the end of the queue.
        """

        with self._condition:
            self._queue.append(request)
            self._condition.notify()

    # ============================================================
    # GET
    # ============================================================

    def get(
        self,
        timeout: Optional[float] = None,
    ) -> Optional[APIRequest]:
        """
        Remove and return the next request.

        If the queue is empty, wait until a request becomes
        available or until timeout expires.

        Returns:
            APIRequest if available.
            None if timeout expires.
        """

        with self._condition:

            if not self._queue:
                notified = self._condition.wait(timeout)

                if not notified and not self._queue:
                    return None

            if not self._queue:
                return None

            return self._queue.popleft()

    # ============================================================
    # NON-BLOCKING GET
    # ============================================================

    def get_nowait(self) -> Optional[APIRequest]:
        """
        Return the next request immediately.

        Returns None if the queue is empty.
        """

        with self._condition:

            if not self._queue:
                return None

            return self._queue.popleft()

    # ============================================================
    # PEEK
    # ============================================================

    def peek(self) -> Optional[APIRequest]:
        """
        Look at the next request without removing it.
        """

        with self._condition:

            if not self._queue:
                return None

            return self._queue[0]

    # ============================================================
    # SIZE
    # ============================================================

    def size(self) -> int:
        """
        Return the number of waiting requests.
        """

        with self._condition:
            return len(self._queue)

    def empty(self) -> bool:
        """
        Return True if there are no waiting requests.
        """

        with self._condition:
            return len(self._queue) == 0

    # ============================================================
    # CLEAR
    # ============================================================

    def clear(self) -> None:
        """
        Remove all pending requests.
        """

        with self._condition:
            self._queue.clear()

    # ============================================================
    # INFORMATION
    # ============================================================

    def __len__(self) -> int:
        return self.size()