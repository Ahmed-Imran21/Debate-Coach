from pathlib import Path
from datetime import datetime


class Session:
    """
    Represents one complete debate session.

    A Session object keeps track of:
        - session ID
        - session directory
        - recording path
        - transcription path
        - analysis path
        - session status
        - creation time
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

        # Files belonging to this session
        self.audio_path = (
            self.session_directory / "recording.wav"
        )

        self.transcription_path = (
            self.session_directory / "transcription.json"
        )

        self.analysis_path = (
            self.session_directory / "analysis.json"
        )

        # Session information
        self.created_at = datetime.now()

        self.status = "created"

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
    # Status
    # ---------------------------------

    def start(self):
        """
        Mark the session as active.
        """

        self.status = "recording"

    def finish_recording(self):
        """
        Mark recording as completed.
        """

        self.status = "recorded"

    def finish_transcription(self):
        """
        Mark transcription as completed.
        """

        self.status = "transcribed"

    def finish_analysis(self):
        """
        Mark analysis as completed.
        """

        self.status = "analyzed"

    def complete(self):
        """
        Mark the entire session as completed.
        """

        self.status = "completed"

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
        session_id="session_20260826_230000"
    )

    session.create_directory()

    print()
    print("Session created:")
    print(session)

    print()
    print(f"Session ID: {session.session_id}")
    print(f"Session directory: {session.session_directory}")
    print(f"Audio path: {session.audio_path}")
    print(
        f"Transcription path: "
        f"{session.transcription_path}"
    )
    print(
        f"Analysis path: "
        f"{session.analysis_path}"
    )