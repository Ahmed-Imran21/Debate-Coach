import json
import os
import threading

from pathlib import Path
from datetime import datetime


# ============================================================
# STATUS CONSTANTS
# ============================================================
#
# Extends the original CLI lifecycle (created -> recording ->
# recorded -> transcribed -> analyzed -> completed) with the
# additional stages the server pipeline goes through, plus a
# transient "waiting_for_api_capacity" status surfaced whenever
# every API key is temporarily out of capacity (see api/client.py
# and QueuedRequest). "failed" can be reached from any stage.

STATUS_CREATED = "created"
STATUS_RECORDING = "recording"            # CLI flow only
STATUS_RECORDED = "recorded"              # CLI flow only
STATUS_UPLOADED = "uploaded"              # server flow only
STATUS_TRANSCRIBING = "transcribing"
STATUS_TRANSCRIBED = "transcribed"
STATUS_ANALYZING_AUDIO = "analyzing_audio"
STATUS_ANALYZED = "analyzed"
STATUS_CALCULATING_METRICS = "calculating_metrics"
STATUS_METRICS_CALCULATED = "metrics_calculated"
STATUS_ANALYZING_SPEECH = "analyzing_speech"
STATUS_SPEECH_ANALYZED = "speech_analyzed"
STATUS_COACHING = "coaching"
STATUS_WAITING_FOR_API_CAPACITY = "waiting_for_api_capacity"
STATUS_COMPLETED = "completed"
STATUS_FAILED = "failed"


class Session:
    """
    Represents one complete debate session.

    Thread-safety:
        Under the server, one background thread runs the
        pipeline for a session while request-handler threads may
        concurrently read its status. All mutation goes through
        _set_status() under a per-instance lock, and save() writes
        session.json atomically (write to a temp file, then
        os.replace) so a concurrent reader never sees a partially
        written file.
    """

    def __init__(self, session_id, base_directory="sessions"):
        """
        Create a new Session object.

        Parameters:
            session_id (str):
                Unique ID for this debate session.

            base_directory (str or Path):
                Root directory where all sessions are stored.
        """

        self.session_id = session_id

        # Root directory containing all sessions
        self.base_directory = Path(base_directory)

        # Directory belonging specifically to this session
        self.session_directory = (
            self.base_directory / self.session_id
        )

        # Files belonging to this session.
        # These are always deterministic functions of
        # session_directory, so they never need to be persisted
        # or "restored" separately from session.json.
        self.audio_path = (
            self.session_directory / "recording.wav"
        )

        self.transcription_path = (
            self.session_directory / "transcription.json"
        )

        self.analysis_path = (
            self.session_directory / "analysis.json"
        )

        self.raw_metrics_path = (
            self.session_directory / "raw_metrics.json"
        )

        self.speech_content_path = (
            self.session_directory / "speech_content.json"
        )

        self.feedback_path = (
            self.session_directory / "feedback.json"
        )

        # Session metadata file
        self.session_json_path = (
            self.session_directory / "session.json"
        )

        # Session information
        self.created_at = datetime.now()
        self.updated_at = self.created_at

        self.status = STATUS_CREATED

        # Populated if the pipeline fails at any stage.
        self.error = None

        # Populated while status == waiting_for_api_capacity.
        self.estimated_wait_seconds = None

        # Guards all mutation + save() below.
        self._lock = threading.RLock()

    # ---------------------------------
    # Session directory
    # ---------------------------------

    def create_directory(self):
        """
        Create the directory for this session.
        """

        self.session_directory.mkdir(
            parents=True,
            exist_ok=True
        )

    # ---------------------------------
    # Save session metadata
    # ---------------------------------

    def save(self):
        """
        Save the current session metadata to session.json.

        Writes to a temporary file in the same directory and
        then atomically renames it into place, so a concurrent
        reader (e.g. a status-polling HTTP request) never
        observes a half-written file.
        """

        with self._lock:

            session_data = {
                "session_id": self.session_id,

                "created_at": (
                    self.created_at.isoformat()
                ),

                "updated_at": (
                    self.updated_at.isoformat()
                ),

                "status": self.status,

                "error": self.error,

                "estimated_wait_seconds": (
                    self.estimated_wait_seconds
                ),

                "files": {
                    "audio": self.audio_path.name,
                    "transcription": self.transcription_path.name,
                    "analysis": self.analysis_path.name,
                    "raw_metrics": self.raw_metrics_path.name,
                    "speech_content": self.speech_content_path.name,
                    "feedback": self.feedback_path.name,
                }
            }

            tmp_path = self.session_json_path.with_suffix(
                ".json.tmp"
            )

            with open(
                tmp_path,
                "w",
                encoding="utf-8"
            ) as file:

                json.dump(
                    session_data,
                    file,
                    indent=4
                )

            os.replace(
                tmp_path,
                self.session_json_path
            )

    # ---------------------------------
    # Load session
    # ---------------------------------

    @classmethod
    def load(cls, session_id, base_directory="sessions"):
        """
        Load an existing session from session.json.

        Parameters:
            session_id (str):
                ID of the session to load.

            base_directory (str or Path):
                Root directory where all sessions are stored.

        Returns:
            Session:
                Session object reconstructed from session.json.
        """

        # File paths are re-derived deterministically in
        # __init__ from session_directory, so nothing needs to
        # be separately restored for them.
        session = cls(
            session_id=session_id,
            base_directory=base_directory
        )

        if not session.session_json_path.exists():

            raise FileNotFoundError(
                f"session.json for session "
                f"'{session_id}' does not exist."
            )

        with open(
            session.session_json_path,
            "r",
            encoding="utf-8"
        ) as file:

            session_data = json.load(file)

        session.created_at = datetime.fromisoformat(
            session_data["created_at"]
        )

        session.updated_at = datetime.fromisoformat(
            session_data.get(
                "updated_at",
                session_data["created_at"],
            )
        )

        session.status = session_data["status"]

        session.error = session_data.get("error")

        session.estimated_wait_seconds = session_data.get(
            "estimated_wait_seconds"
        )

        return session

    # ---------------------------------
    # Internal status transition helper
    # ---------------------------------

    def _set_status(self, status, **extra):

        with self._lock:

            self.status = status
            self.updated_at = datetime.now()

            for key, value in extra.items():
                setattr(self, key, value)

            self.save()

    # ---------------------------------
    # CLI lifecycle (main.py) — unchanged names/behavior
    # ---------------------------------

    def start(self):
        """
        Mark the session as actively recording (CLI flow).
        """

        self._set_status(STATUS_RECORDING)

    def finish_recording(self):
        """
        Mark recording as completed (CLI flow).
        """

        self._set_status(STATUS_RECORDED)

    def finish_transcription(self):
        """
        Mark transcription as completed.
        """

        self._set_status(STATUS_TRANSCRIBED)

    def finish_analysis(self):
        """
        Mark audio analysis as completed.
        """

        self._set_status(STATUS_ANALYZED)

    def complete(self):
        """
        Mark the entire session as completed.
        """

        self._set_status(
            STATUS_COMPLETED,
            error=None,
            estimated_wait_seconds=None,
        )

    # ---------------------------------
    # Server pipeline lifecycle (server/pipeline.py)
    # ---------------------------------

    def mark_uploaded(self):
        """
        Mark that the raw audio upload has been saved and
        normalized, and is ready for the pipeline.
        """

        self._set_status(STATUS_UPLOADED)

    def mark_transcribing(self):
        self._set_status(STATUS_TRANSCRIBING)

    def mark_analyzing_audio(self):
        self._set_status(STATUS_ANALYZING_AUDIO)

    def mark_calculating_metrics(self):
        self._set_status(STATUS_CALCULATING_METRICS)

    def mark_metrics_calculated(self):
        self._set_status(STATUS_METRICS_CALCULATED)

    def mark_analyzing_speech(self):
        self._set_status(STATUS_ANALYZING_SPEECH)

    def mark_speech_analyzed(self):
        self._set_status(STATUS_SPEECH_ANALYZED)

    def mark_coaching(self):
        self._set_status(STATUS_COACHING)

    def mark_waiting_for_capacity(self, estimated_wait_seconds):
        """
        Called via the on_queued callback whenever every
        compatible API key is temporarily out of capacity.

        The pipeline stage resumes and overwrites this status
        as soon as the underlying APIClient.generate() call
        actually completes, so this is purely a transient,
        user-visible "hang tight" state.
        """

        self._set_status(
            STATUS_WAITING_FOR_API_CAPACITY,
            estimated_wait_seconds=float(
                estimated_wait_seconds
            ),
        )

    def mark_failed(self, error):
        """
        Mark the session as failed, recording a short error
        summary for the status endpoint.
        """

        self._set_status(
            STATUS_FAILED,
            error=str(error),
        )

    # ---------------------------------
    # Server-facing serialization
    # ---------------------------------

    def to_status_dict(self):
        """
        Return a plain dict suitable for a JSON status response.
        """

        with self._lock:

            return {
                "session_id": self.session_id,
                "status": self.status,
                "created_at": self.created_at.isoformat(),
                "updated_at": self.updated_at.isoformat(),
                "error": self.error,
                "estimated_wait_seconds": (
                    self.estimated_wait_seconds
                ),
            }

    # ---------------------------------
    # Representation
    # ---------------------------------

    def __repr__(self):
        """
        Return a useful representation of the Session.
        """

        return (
            f"Session("
            f"id='{self.session_id}', "
            f"status='{self.status}'"
            f")"
        )


# ---------------------------------
# Test Session
# ---------------------------------

if __name__ == "__main__":

    session = Session(
        session_id="session_test"
    )

    session.create_directory()
    session.save()

    print()
    print("Session created:")
    print(session)

    print()
    print(f"Session ID: {session.session_id}")
    print(
        f"Session directory: "
        f"{session.session_directory}"
    )
    print(
        f"Session JSON: "
        f"{session.session_json_path}"
    )
    print(
        f"Audio path: "
        f"{session.audio_path}"
    )
    print(
        f"Transcription path: "
        f"{session.transcription_path}"
    )
    print(
        f"Analysis path: "
        f"{session.analysis_path}"
    )