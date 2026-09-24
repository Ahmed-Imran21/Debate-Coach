from pathlib import Path
from uuid import uuid4

from session import Session


class SessionManager:
    """
    Responsible for creating and managing debate sessions.

    Session IDs are UUID-based so that concurrent session
    creation from multiple simultaneous users can never collide
    — the previous timestamp-based ID
    (session_%Y%m%d_%H%M%S, one-second resolution) could produce
    the same ID for two users starting within the same second.

    Backend integration:
        create_session() can take an externally-supplied
        session_id (the backend's Postgres `sessions.id`, a
        UUID) and user_id (the backend's `users.id`) so the local
        session directory and the Postgres row represent the same
        logical session under the same ID. If session_id is not
        supplied, one is still generated locally exactly as
        before — nothing about existing CLI/local-only usage
        changes.
    """

    def __init__(self, base_directory="sessions"):
        """
        Initialize the SessionManager.

        Parameters:
            base_directory (str or Path):
                Root directory where all sessions are stored.
        """

        self.base_directory = Path(base_directory)

        self.base_directory.mkdir(
            parents=True,
            exist_ok=True
        )

    # ---------------------------------
    # Create session
    # ---------------------------------

    def create_session(self, session_id=None, user_id=None):
        """
        Create a new debate session.

        Parameters:
            session_id (str, optional):
                Use this exact ID instead of generating one.
                Pass the backend's Postgres `sessions.id` here so
                the local session directory and the Postgres row
                refer to the same session.

            user_id (str, optional):
                Owning user's ID (the backend's `users.id`).
                Required later if you plan to call
                session.sync_artifacts_to_storage().

        Returns:
            Session:
                A newly created Session object.

        Raises:
            FileExistsError:
                If session_id is supplied and a session with that
                ID already exists on disk.
        """

        if session_id is None:
            session_id = f"session_{uuid4().hex}"

        elif (self.base_directory / session_id).exists():

            raise FileExistsError(
                f"A session directory already exists for "
                f"session_id '{session_id}'."
            )

        session = Session(
            session_id=session_id,
            base_directory=self.base_directory,
            user_id=user_id,
        )

        session.create_directory()
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


# ---------------------------------
# Test Session Manager
# ---------------------------------

if __name__ == "__main__":

    manager = SessionManager()

    session = manager.create_session()

    print()
    print("Session object:")
    print(session)

    exists = manager.session_exists(
        session.session_id
    )

    print()
    print(
        f"Session exists: {exists}"
    )

    sessions = manager.list_sessions()

    print()
    print("All sessions:")

    for session_id in sessions:
        print(f"- {session_id}")