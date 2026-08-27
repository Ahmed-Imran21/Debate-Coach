from pathlib import Path
from datetime import datetime

from session import Session


class SessionManager:
    """
    Responsible for creating and managing debate sessions.
    """

    def __init__(self, base_directory="sessions"):
        """
        Initialize the SessionManager.

        Parameters:
            base_directory (str or Path):
                Root directory where all sessions are stored.
        """

        self.base_directory = Path(base_directory)

        # Make sure the main sessions directory exists
        self.base_directory.mkdir(
            parents=True,
            exist_ok=True
        )

    # ---------------------------------
    # Create session
    # ---------------------------------

    def create_session(self):
        """
        Create a new debate session.

        Returns:
            Session:
                A newly created Session object.
        """

        # Generate a unique session ID
        session_id = datetime.now().strftime(
            "session_%Y%m%d_%H%M%S"
        )

        # Create the Session object
        session = Session(
            session_id=session_id,
            base_directory=self.base_directory
        )

        # Create the session's directory
        session.create_directory()

        # Save initial session metadata
        session.save()

        print()
        print("New session created.")
        print(f"Session ID: {session.session_id}")
        print(
            f"Session directory: "
            f"{session.session_directory}"
        )

        return session

    # ---------------------------------
    # Load existing session
    # ---------------------------------


    def load_session(self, session_id):
        """
        Load an existing session.

        Parameters:
            session_id (str):
                ID of the session to load.

        Returns:
            Session:
                Session object representing the existing session.

        Raises:
            FileNotFoundError:
                If the session directory or session.json
                does not exist.
        """

        session_directory = (
            self.base_directory / session_id
        )

        if not session_directory.exists():

            raise FileNotFoundError(
                f"Session '{session_id}' "
                f"does not exist."
            )

        # Load the session from its saved metadata
        session = Session.load(
            session_id=session_id,
            base_directory=self.base_directory
        )

        return session

    # ---------------------------------
    # Check if session exists
    # ---------------------------------

    def session_exists(self, session_id):
        """
        Check whether a session exists.

        Parameters:
            session_id (str):
                ID of the session.

        Returns:
            bool:
                True if the session exists,
                otherwise False.
        """

        session_directory = (
            self.base_directory / session_id
        )

        return session_directory.exists()

    # ---------------------------------
    # List sessions
    # ---------------------------------

    def list_sessions(self):
        """
        Return the IDs of all existing sessions.

        Returns:
            list:
                List of session IDs.
        """

        sessions = []

        for path in self.base_directory.iterdir():

            if path.is_dir():

                sessions.append(
                    path.name
                )

        return sessions




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

    # Restore saved session information
    session.created_at = datetime.fromisoformat(
        session_data["created_at"]
    )

    session.status = session_data["status"]

    return session

# ---------------------------------
# Test Session Manager
# ---------------------------------

if __name__ == "__main__":

    manager = SessionManager()

    # Create a new session
    session = manager.create_session()

    print()
    print("Session object:")
    print(session)

    # Check whether the session exists
    exists = manager.session_exists(
        session.session_id
    )

    print()
    print(
        f"Session exists: {exists}"
    )

    # List all sessions
    sessions = manager.list_sessions()

    print()
    print("All sessions:")

    for session_id in sessions:
        print(f"- {session_id}")