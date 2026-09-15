"""
Process-wide holder for the shared API system.

There is exactly one APIClient per process. It owns:

    - the LLM key pool          (api/key_registry.py)
    - the LLM scheduler         (api/scheduler.py)
    - the LLM request queue     (api/request_queue.py)
    - the Whisper key pool      (api/whisper.py)
    - the Whisper queue         (api/whisper.py)

All of that state is round-robin across the keys discovered in
the environment. Creating a second APIClient would create a
second, independent view of the same quota and the rate limits
would stop being enforced correctly, so the client is created
once in the FastAPI lifespan and read from here everywhere else.
"""

from typing import Optional

from api.client import APIClient


_api_client: Optional[APIClient] = None


def start() -> APIClient:
    """
    Create the shared APIClient. Called once, from the FastAPI
    lifespan handler on startup.
    """

    global _api_client

    if _api_client is not None:
        return _api_client

    _api_client = APIClient()

    return _api_client


def get_api_client() -> APIClient:
    """
    Return the shared APIClient.
    """

    if _api_client is None:
        raise RuntimeError(
            "APIClient has not been started. This is called "
            "before the FastAPI lifespan handler ran."
        )

    return _api_client


def key_count() -> int:

    if _api_client is None:
        return 0

    return len(_api_client.get_keys())


def status() -> dict:
    """
    Snapshot of pool health, used by the /v1/status endpoint.
    """

    if _api_client is None:
        return {
            "ready": False,
            "llm_keys": 0,
            "llm_queue_depth": 0,
            "whisper_queue_depth": 0,
        }

    return {
        "ready": True,
        "llm_keys": len(_api_client.get_keys()),
        "llm_queue_depth": _api_client.get_queue_size(),
        "whisper_queue_depth": (
            _api_client.get_whisper_queue_size()
        ),
    }


def shutdown() -> None:
    """
    Drain both queues and stop the workers. Called from the
    lifespan handler on shutdown.
    """

    global _api_client

    if _api_client is None:
        return

    _api_client.shutdown()
    _api_client = None
