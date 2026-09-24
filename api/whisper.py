from __future__ import annotations

import os
import queue
import re
import threading

from collections import deque
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Optional

from dotenv import load_dotenv
from groq import Groq


# ============================================================
# ENVIRONMENT
# ============================================================

load_dotenv()


# ============================================================
# CONFIGURATION
# ============================================================

WHISPER_MODEL = "whisper-large-v3"

# Groq's documented base limits for whisper-large-v3 are:
#
# RPM = requests per minute
# RPD = requests per day
# ASH = audio seconds per hour
# ASD = audio seconds per day
#
# These are intentionally configurable through environment
# variables because Groq limits can differ by organization/
# project/plan.

WHISPER_RPM = int(
    os.environ.get(
        "GROQ_WHISPER_RPM",
        "20",
    )
)

WHISPER_RPD = int(
    os.environ.get(
        "GROQ_WHISPER_RPD",
        "2000",
    )
)

WHISPER_ASH = int(
    os.environ.get(
        "GROQ_WHISPER_ASH",
        "7200",
    )
)

WHISPER_ASD = int(
    os.environ.get(
        "GROQ_WHISPER_ASD",
        "28800",
    )
)

# Groq currently documents 100 MB for the developer tier.
# Keep this configurable.
WHISPER_MAX_FILE_MB = float(
    os.environ.get(
        "GROQ_WHISPER_MAX_FILE_MB",
        "100",
    )
)

# Number of concurrent Whisper API operations.
#
# This is deliberately larger than the number of keys because
# workers that cannot acquire capacity simply wait. In normal
# operation the key pool determines how many requests can
# actually execute simultaneously.
WHISPER_WORKERS = int(
    os.environ.get(
        "WHISPER_WORKERS",
        "8",
    )
)

# How frequently the queue workers wake up while waiting for
# capacity.
QUEUE_WAIT_SECONDS = float(
    os.environ.get(
        "WHISPER_QUEUE_WAIT_SECONDS",
        "0.5",
    )
)


# ============================================================
# WHISPER KEY
# ============================================================

@dataclass
class WhisperKey:
    """
    Represents one Groq Whisper API key.

    The pool tracks request/audio usage independently for
    scheduling purposes.

    Important:
        Groq may enforce these limits at the organization
        level rather than independently per API key. Therefore
        this local accounting is primarily used to distribute
        work safely and avoid hammering one key.
    """

    id: str
    key: str

    rpm: int = WHISPER_RPM
    rpd: int = WHISPER_RPD

    ash: int = WHISPER_ASH
    asd: int = WHISPER_ASD

    enabled: bool = True

    cooldown_until: Optional[datetime] = None

    # Each event is:
    #
    # (timestamp, audio_seconds)
    #
    # Used for rolling-window accounting.
    minute_events: deque = field(
        default_factory=deque
    )

    hour_events: deque = field(
        default_factory=deque
    )

    day_events: deque = field(
        default_factory=deque
    )

    # Requests currently executing with this key.
    active_requests: int = 0

    # Total successful requests assigned to this key.
    total_requests: int = 0

    # Total audio seconds assigned to this key.
    total_audio_seconds: float = 0.0


# ============================================================
# TRANSCRIPTION RESULT
# ============================================================

@dataclass
class WhisperResult:
    """
    Normalized result returned by WhisperClient.
    """

    text: str

    language: Optional[str] = None

    language_probability: Optional[float] = None

    segments: list[dict[str, Any]] = field(
        default_factory=list
    )

    raw_response: Any = None

    api_key_id: Optional[str] = None


# ============================================================
# INTERNAL QUEUED REQUEST
# ============================================================

@dataclass
class _WhisperRequest:
    """
    One transcription operation waiting for a Whisper key.
    """

    audio_path: Path

    language: Optional[str]

    prompt: Optional[str]

    temperature: float

    event: threading.Event = field(
        default_factory=threading.Event
    )

    result: Optional[WhisperResult] = None

    error: Optional[Exception] = None


# ============================================================
# WHISPER CLIENT
# ============================================================

class WhisperClient:
    """
    Central Groq Whisper gateway.

    Responsibilities:

        - load multiple Whisper API keys
        - maintain a circular key pool
        - maintain a FIFO request queue
        - select an available key
        - enforce local request/audio capacity
        - handle cooldowns
        - execute Groq Whisper requests
        - distribute requests across keys
        - support concurrent sessions

    This is intentionally separate from the LLM APIClient
    because Whisper uses audio-second quotas rather than
    token quotas.
    """

    KEY_PREFIX = "GROQ_WHISPER_LARGE_V3_KEY_"

    def __init__(
        self,
        worker_count: int = WHISPER_WORKERS,
    ):

        if worker_count < 1:
            raise ValueError(
                "worker_count must be at least 1."
            )

        self._lock = threading.Condition()

        self._keys: list[WhisperKey] = []

        # Circular ordering of keys.
        #
        # Example:
        #
        # W1 -> W2 -> W3 -> W1 -> ...
        #
        self._key_rotation: deque[str] = deque()

        # FIFO waiting queue.
        self._queue: queue.Queue[
            Optional[_WhisperRequest]
        ] = queue.Queue()

        self._stop_event = threading.Event()

        self._workers: list[threading.Thread] = []

        self._load_keys()

        if not self._keys:
            raise RuntimeError(
                "No Groq Whisper API keys were found.\n\n"
                "Expected environment variables such as:\n"
                "  GROQ_WHISPER_LARGE_V3_KEY_1\n"
                "  GROQ_WHISPER_LARGE_V3_KEY_2\n"
                "  GROQ_WHISPER_LARGE_V3_KEY_3\n"
            )

        for key in self._keys:
            self._key_rotation.append(key.id)

        print(
            f"Loaded {len(self._keys)} Groq Whisper API key(s)."
        )

        # -------------------------------------------------
        # Start queue workers
        # -------------------------------------------------

        for index in range(worker_count):

            worker = threading.Thread(
                target=self._worker_loop,
                name=f"WhisperWorker-{index + 1}",
                daemon=True,
            )

            worker.start()

            self._workers.append(worker)

    # ========================================================
    # KEY LOADING
    # ========================================================

    def _load_keys(self) -> None:
        """
        Automatically discover:

            GROQ_WHISPER_LARGE_V3_KEY_1
            GROQ_WHISPER_LARGE_V3_KEY_2
            GROQ_WHISPER_LARGE_V3_KEY_3
            ...

        Adding KEY_4 requires no Python code change.
        """

        pattern = re.compile(
            rf"^{re.escape(self.KEY_PREFIX)}(\d+)$"
        )

        discovered: list[tuple[int, str, str]] = []

        for env_name, env_value in os.environ.items():

            match = pattern.match(env_name)

            if not match:
                continue

            if not env_value:
                continue

            number = int(match.group(1))

            discovered.append(
                (
                    number,
                    env_name,
                    env_value,
                )
            )

        discovered.sort(
            key=lambda item: item[0]
        )

        for number, _, value in discovered:

            self._keys.append(
                WhisperKey(
                    id=(
                        "groq_whisper_large_v3_"
                        f"{number}"
                    ),
                    key=value,
                )
            )

    # ========================================================
    # PUBLIC TRANSCRIPTION API
    # ========================================================

    def transcribe(
        self,
        audio_path: str | Path,
        language: Optional[str] = None,
        prompt: Optional[str] = None,
        temperature: float = 0.0,
        max_wait_seconds: Optional[float] = None,
    ) -> WhisperResult:
        """
        Queue and execute one Whisper transcription.

        The caller blocks until the transcription is complete.

        Multiple sessions can call this method concurrently.
        Requests are placed into the central FIFO queue and
        workers distribute them across the Whisper key pool.
        """

        audio_path = Path(audio_path)

        self._validate_audio_file(
            audio_path
        )

        request = _WhisperRequest(
            audio_path=audio_path,
            language=language,
            prompt=prompt,
            temperature=temperature,
        )

        self._queue.put(request)

        completed = request.event.wait(
            timeout=max_wait_seconds
        )

        if not completed:

            raise TimeoutError(
                "Timed out waiting for the Groq Whisper "
                "transcription queue."
            )

        if request.error is not None:
            raise request.error

        if request.result is None:
            raise RuntimeError(
                "Whisper request completed without a result."
            )

        return request.result

    # ========================================================
    # FILE VALIDATION
    # ========================================================

    def _validate_audio_file(
        self,
        audio_path: Path,
    ) -> None:

        if not audio_path.exists():

            raise FileNotFoundError(
                f"Audio file does not exist: "
                f"{audio_path}"
            )

        if not audio_path.is_file():

            raise ValueError(
                f"Audio path is not a file: "
                f"{audio_path}"
            )

        file_size_mb = (
            audio_path.stat().st_size
            / (1024 * 1024)
        )

        if file_size_mb > WHISPER_MAX_FILE_MB:

            raise ValueError(
                f"Audio file is {file_size_mb:.2f} MB, "
                f"which exceeds the configured Groq Whisper "
                f"limit of {WHISPER_MAX_FILE_MB:.2f} MB."
            )

    # ========================================================
    # WORKER LOOP
    # ========================================================

    def _worker_loop(self) -> None:

        while not self._stop_event.is_set():

            try:

                request = self._queue.get(
                    timeout=0.5
                )

            except queue.Empty:
                continue

            if request is None:

                self._queue.task_done()

                break

            try:

                self._process_request(
                    request
                )

            except Exception as error:

                request.error = error

                request.event.set()

            finally:

                self._queue.task_done()

    # ========================================================
    # PROCESS REQUEST
    # ========================================================

    def _process_request(
        self,
        request: _WhisperRequest,
    ) -> None:

        audio_seconds = (
            self._get_audio_duration_seconds(
                request.audio_path
            )
        )

        key = self._acquire_key(
            audio_seconds=audio_seconds
        )

        try:

            result = self._execute(
                key=key,
                request=request,
            )

            request.result = result

        except Exception as error:

            # ------------------------------------------------
            # If Groq reports a rate limit, put this key into
            # a cooldown so other keys are preferred.
            # ------------------------------------------------

            if self._is_rate_limit_error(error):

                retry_after = (
                    self._get_retry_after(error)
                )

                self._set_cooldown(
                    key,
                    retry_after,
                )

            raise

        finally:

            self._release_key(
                key
            )

            with self._lock:
                self._lock.notify_all()

        request.event.set()

    # ========================================================
    # KEY ACQUISITION
    # ========================================================

    def _acquire_key(
        self,
        audio_seconds: float,
    ) -> WhisperKey:
        """
        Select a key using the circular pool.

        The algorithm:

            1. Start at the current front of the circular
               key queue.
            2. Inspect each key once.
            3. Skip disabled/cooldown/full keys.
            4. Select the first compatible key.
            5. Move the selected key to the back.
            6. If none is available, wait and retry.

        This gives fair round-robin distribution while still
        respecting capacity.
        """

        while not self._stop_event.is_set():

            with self._lock:

                self._cleanup_usage()

                key_count = len(
                    self._key_rotation
                )

                for _ in range(key_count):

                    key_id = (
                        self._key_rotation.popleft()
                    )

                    self._key_rotation.append(
                        key_id
                    )

                    key = self._get_key_by_id(
                        key_id
                    )

                    if key is None:
                        continue

                    if not self._can_handle(
                        key,
                        audio_seconds,
                    ):
                        continue

                    key.active_requests += 1

                    return key

                # ------------------------------------------------
                # No key is currently available.
                # Calculate the shortest estimated wait.
                # ------------------------------------------------

                wait_seconds = (
                    self._estimate_wait(
                        audio_seconds
                    )
                )

                self._lock.wait(
                    timeout=min(
                        max(
                            wait_seconds,
                            0.1,
                        ),
                        QUEUE_WAIT_SECONDS,
                    )
                )

        raise RuntimeError(
            "WhisperClient is shutting down."
        )

    # ========================================================
    # KEY RELEASE
    # ========================================================

    def _release_key(
        self,
        key: WhisperKey,
    ) -> None:

        with self._lock:

            key.active_requests = max(
                0,
                key.active_requests - 1,
            )

            self._lock.notify_all()

    # ========================================================
    # CAPACITY CHECK
    # ========================================================

    def _can_handle(
        self,
        key: WhisperKey,
        audio_seconds: float,
    ) -> bool:

        if not key.enabled:
            return False

        now = datetime.utcnow()

        if (
            key.cooldown_until is not None
            and now < key.cooldown_until
        ):
            return False

        minute_requests = sum(
            1
            for timestamp, _ in key.minute_events
            if timestamp
            > now - timedelta(seconds=60)
        )

        day_requests = len(
            key.day_events
        )

        hour_audio = sum(
            duration
            for timestamp, duration
            in key.hour_events
            if timestamp
            > now - timedelta(hours=1)
        )

        day_audio = sum(
            duration
            for _, duration
            in key.day_events
        )

        if (
            minute_requests + key.active_requests
            >= key.rpm
        ):
            return False

        if (
            day_requests + key.active_requests
            >= key.rpd
        ):
            return False

        if (
            hour_audio + audio_seconds
            > key.ash
        ):
            return False

        if (
            day_audio + audio_seconds
            > key.asd
        ):
            return False

        return True

    # ========================================================
    # WAIT ESTIMATION
    # ========================================================

    def _estimate_wait(
        self,
        audio_seconds: float,
    ) -> float:

        now = datetime.utcnow()

        waits = []

        for key in self._keys:

            if not key.enabled:
                continue

            if (
                key.cooldown_until is not None
                and now < key.cooldown_until
            ):

                waits.append(
                    (
                        key.cooldown_until
                        - now
                    ).total_seconds()
                )

                continue

            minute_events = sorted(
                key.minute_events,
                key=lambda item: item[0],
            )

            if (
                len(minute_events)
                + key.active_requests
                >= key.rpm
            ):

                if minute_events:

                    free_at = (
                        minute_events[0][0]
                        + timedelta(seconds=60)
                    )

                    waits.append(
                        max(
                            0.0,
                            (
                                free_at - now
                            ).total_seconds(),
                        )
                    )

                else:

                    waits.append(60.0)

                continue

            hour_audio = sum(
                duration
                for timestamp, duration
                in key.hour_events
                if timestamp
                > now - timedelta(hours=1)
            )

            if hour_audio + audio_seconds > key.ash:

                oldest = sorted(
                    key.hour_events,
                    key=lambda item: item[0],
                )

                if oldest:

                    free_at = (
                        oldest[0][0]
                        + timedelta(hours=1)
                    )

                    waits.append(
                        max(
                            0.0,
                            (
                                free_at - now
                            ).total_seconds(),
                        )
                    )

                continue

            # This key should be available very soon.
            waits.append(0.0)

        if not waits:

            return QUEUE_WAIT_SECONDS

        return min(waits)

    # ========================================================
    # EXECUTION
    # ========================================================

    def _execute(
        self,
        key: WhisperKey,
        request: _WhisperRequest,
    ) -> WhisperResult:

        client = Groq(
            api_key=key.key
        )

        filename = request.audio_path.name

        with open(
            request.audio_path,
            "rb",
        ) as audio_file:

            response = (
                client.audio.transcriptions.create(
                    file=(
                        filename,
                        audio_file.read(),
                    ),
                    model=WHISPER_MODEL,
                    response_format="verbose_json",
                    timestamp_granularities=[
                        "segment",
                        "word",
                    ],
                    language=request.language,
                    prompt=request.prompt,
                    temperature=request.temperature,
                )
            )

        audio_seconds = (
            self._get_audio_duration_seconds(
                request.audio_path
            )
        )

        self._record_usage(
            key=key,
            audio_seconds=audio_seconds,
        )

        segments = (
            self._normalize_segments(
                response
            )
        )

        text = getattr(
            response,
            "text",
            "",
        ) or ""

        language = getattr(
            response,
            "language",
            None,
        )

        language_probability = getattr(
            response,
            "language_probability",
            None,
        )

        return WhisperResult(
            text=text,
            language=language,
            language_probability=(
                language_probability
            ),
            segments=segments,
            raw_response=response,
            api_key_id=key.id,
        )

    # ========================================================
    # RESPONSE NORMALIZATION
    # ========================================================

    @staticmethod
    def _field(
        source: Any,
        name: str,
        default: Any = None,
    ) -> Any:
        """
        Groq returns verbose_json pieces as plain dicts, while
        other SDK builds return objects. getattr() on a dict
        silently yields the default, which previously wiped every
        segment timing and left the whole transcript unusable, so
        read both shapes explicitly.
        """

        if isinstance(source, dict):
            return source.get(name, default)

        return getattr(source, name, default)

    @classmethod
    def _normalize_words(
        cls,
        raw_words: Any,
    ) -> list[dict[str, Any]]:

        normalized = []

        for word in raw_words or []:

            normalized.append(
                {
                    "word": cls._field(word, "word", "") or "",
                    "start": cls._field(word, "start"),
                    "end": cls._field(word, "end"),
                    "probability": cls._field(
                        word,
                        "probability",
                    ),
                }
            )

        return normalized

    @staticmethod
    def _attach_loose_words(
        segments: list[dict[str, Any]],
        loose_words: list[dict[str, Any]],
    ) -> None:
        """
        With timestamp_granularities=["segment", "word"], Groq
        returns word timings in one top-level list rather than
        nested per segment. raw_metrics reads them off each
        segment (segment.get("words", [])), so map them back by
        time span or every per-word metric silently sees nothing.
        """

        if not loose_words or not segments:
            return

        if any(segment["words"] for segment in segments):
            return

        for word in loose_words:

            target = None

            for segment in segments:

                start = segment["start"]
                end = segment["end"]

                if (
                    word["start"] is not None
                    and start is not None
                    and end is not None
                    and start <= word["start"] <= end
                ):
                    target = segment
                    break

            # Anything unplaceable (no timing, or past the last
            # segment boundary) still belongs in the transcript.
            if target is None:
                target = segments[-1]

            target["words"].append(word)

    @classmethod
    def _normalize_segments(
        cls,
        response: Any,
    ) -> list[dict[str, Any]]:

        raw_segments = cls._field(response, "segments")

        if raw_segments is None:
            return []

        normalized = []

        for segment in raw_segments:

            normalized.append(
                {
                    "start": cls._field(segment, "start"),
                    "end": cls._field(segment, "end"),
                    "text": (
                        cls._field(segment, "text", "") or ""
                    ).strip(),
                    "words": cls._normalize_words(
                        cls._field(segment, "words")
                    ),
                }
            )

        cls._attach_loose_words(
            normalized,
            cls._normalize_words(
                cls._field(response, "words")
            ),
        )

        return normalized

    # ========================================================
    # USAGE
    # ========================================================

    def _record_usage(
        self,
        key: WhisperKey,
        audio_seconds: float,
    ) -> None:

        now = datetime.utcnow()

        event = (
            now,
            audio_seconds,
        )

        with self._lock:

            key.minute_events.append(
                event
            )

            key.hour_events.append(
                event
            )

            key.day_events.append(
                event
            )

            key.total_requests += 1

            key.total_audio_seconds += (
                audio_seconds
            )

            self._cleanup_usage()

            self._lock.notify_all()

    # ========================================================
    # CLEANUP
    # ========================================================

    def _cleanup_usage(self) -> None:

        now = datetime.utcnow()

        minute_cutoff = (
            now - timedelta(seconds=60)
        )

        hour_cutoff = (
            now - timedelta(hours=1)
        )

        day_cutoff = (
            now - timedelta(days=1)
        )

        for key in self._keys:

            while (
                key.minute_events
                and key.minute_events[0][0]
                <= minute_cutoff
            ):

                key.minute_events.popleft()

            while (
                key.hour_events
                and key.hour_events[0][0]
                <= hour_cutoff
            ):

                key.hour_events.popleft()

            while (
                key.day_events
                and key.day_events[0][0]
                <= day_cutoff
            ):

                key.day_events.popleft()

            if (
                key.cooldown_until is not None
                and now >= key.cooldown_until
            ):

                key.cooldown_until = None

    # ========================================================
    # KEY HELPERS
    # ========================================================

    def _get_key_by_id(
        self,
        key_id: str,
    ) -> Optional[WhisperKey]:

        for key in self._keys:

            if key.id == key_id:
                return key

        return None

    def _set_cooldown(
        self,
        key: WhisperKey,
        seconds: float,
    ) -> None:

        with self._lock:

            key.cooldown_until = (
                datetime.utcnow()
                + timedelta(
                    seconds=max(
                        1.0,
                        seconds,
                    )
                )
            )

            self._lock.notify_all()

    # ========================================================
    # AUDIO DURATION
    # ========================================================

    @staticmethod
    def _get_audio_duration_seconds(
        audio_path: Path,
    ) -> float:
        """
        The Debate Coach pipeline normalizes uploads to WAV,
        so we can calculate duration directly without adding
        another dependency.
        """

        import wave

        try:

            with wave.open(
                str(audio_path),
                "rb",
            ) as wav_file:

                frames = wav_file.getnframes()
                sample_rate = wav_file.getframerate()

                if sample_rate <= 0:
                    raise ValueError(
                        "Invalid WAV sample rate."
                    )

                return frames / sample_rate

        except wave.Error as error:

            raise ValueError(
                "Whisper audio must be a valid WAV file "
                "at this point in the Debate Coach pipeline."
            ) from error

    # ========================================================
    # RATE LIMIT ERROR
    # ========================================================

    @staticmethod
    def _is_rate_limit_error(
        error: Exception,
    ) -> bool:

        status_code = getattr(
            error,
            "status_code",
            None,
        )

        if status_code == 429:
            return True

        response = getattr(
            error,
            "response",
            None,
        )

        if response is not None:

            response_status = getattr(
                response,
                "status_code",
                None,
            )

            if response_status == 429:
                return True

        text = str(error).lower()

        phrases = [
            "rate limit",
            "rate_limit",
            "too many requests",
            "429",
            "quota exceeded",
            "resource exhausted",
        ]

        return any(
            phrase in text
            for phrase in phrases
        )

    @staticmethod
    def _get_retry_after(
        error: Exception,
    ) -> float:

        retry_after = getattr(
            error,
            "retry_after",
            None,
        )

        if retry_after is not None:

            try:
                return float(
                    retry_after
                )

            except (
                TypeError,
                ValueError,
            ):
                pass

        response = getattr(
            error,
            "response",
            None,
        )

        if response is not None:

            headers = getattr(
                response,
                "headers",
                None,
            )

            if headers:

                value = headers.get(
                    "retry-after"
                )

                if value is not None:

                    try:
                        return float(
                            value
                        )

                    except (
                        TypeError,
                        ValueError,
                    ):
                        pass

        return 60.0

    # ========================================================
    # STATUS
    # ========================================================

    def get_queue_size(self) -> int:
        return self._queue.qsize()

    def get_status(self) -> list[dict[str, Any]]:
        """
        Return non-secret status information for every
        Whisper key.
        """

        with self._lock:

            self._cleanup_usage()

            now = datetime.utcnow()

            status = []

            for key in self._keys:

                minute_requests = len(
                    key.minute_events
                )

                hour_audio = sum(
                    duration
                    for _, duration
                    in key.hour_events
                )

                day_audio = sum(
                    duration
                    for _, duration
                    in key.day_events
                )

                status.append(
                    {
                        "key_id": key.id,
                        "model": WHISPER_MODEL,
                        "enabled": key.enabled,
                        "active_requests": (
                            key.active_requests
                        ),
                        "cooldown_active": (
                            key.cooldown_until is not None
                            and now < key.cooldown_until
                        ),
                        "requests_this_minute": (
                            minute_requests
                        ),
                        "requests_today": len(
                            key.day_events
                        ),
                        "audio_seconds_this_hour": (
                            hour_audio
                        ),
                        "audio_seconds_today": (
                            day_audio
                        ),
                        "rpm_limit": key.rpm,
                        "rpd_limit": key.rpd,
                        "ash_limit": key.ash,
                        "asd_limit": key.asd,
                        "total_requests": (
                            key.total_requests
                        ),
                        "total_audio_seconds": (
                            key.total_audio_seconds
                        ),
                    }
                )

            return status

    # ========================================================
    # SHUTDOWN
    # ========================================================

    def shutdown(self) -> None:

        self._stop_event.set()

        # Wake workers waiting for capacity.
        with self._lock:
            self._lock.notify_all()

        # Wake workers waiting on queue.get().
        for _ in self._workers:
            self._queue.put(None)

        for worker in self._workers:

            worker.join(
                timeout=5.0
            )

        self._workers.clear()