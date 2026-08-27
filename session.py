from pathlib import Path
from datetime import datetime
import json


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

        # Session metadata file
        self.session_json_path = (
            self.session_directory / "session.json"
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
    # Save session metadata
    # ---------------------------------

    def save(self):
        """
        Save the current session metadata to session.json.
        """

        session_data = {
            "session_id": self.session_id,

            "created_at": (
                self.created_at.isoformat()
            ),

            "status": self.status,

            "files": {
                "audio": self.audio_path.name,
                "transcription": self.transcription_path.name,
                "analysis": self.analysis_path.name
            }
        }

        with open(
            self.session_json_path,
            "w",
            encoding="utf-8"
        ) as file:

            json.dump(
                session_data,
                file,
                indent=4
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

        # Create a Session object using the session ID
        session = cls(
            session_id=session_id,
            base_directory=base_directory
        )

        # Make sure session.json exists
        if not session.session_json_path.exists():

            raise FileNotFoundError(
                f"session.json for session "
                f"'{session_id}' does not exist."
            )

        # Open session.json
        with open(
            session.session_json_path,
            "r",
            encoding="utf-8"
        ) as file:

            session_data = json.load(file)

        # Restore the saved creation time
        session.created_at = datetime.fromisoformat(
            session_data["created_at"]
        )

        # Restore the saved status
        session.status = session_data["status"]

        return session

    # ---------------------------------
    # Status
    # ---------------------------------

    def start(self):
        """
        Mark the session as active.
        """

        self.status = "recording"

        self.save()

    def finish_recording(self):
        """
        Mark recording as completed.
        """

        self.status = "recorded"

        self.save()

    def finish_transcription(self):
        """
        Mark transcription as completed.
        """

        self.status = "transcribed"

        self.save()

    def finish_analysis(self):
        """
        Mark analysis as completed.
        """

        self.status = "analyzed"

        self.save()

    def complete(self):
        """
        Mark the entire session as completed.
        """

        self.status = "completed"

        self.save()

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

    # Save initial session metadata
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