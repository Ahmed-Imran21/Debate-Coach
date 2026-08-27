from pathlib import Path

from session_manager import SessionManager
from audio.recorder import record_audio
from audio.transcriber import transcribe_audio
from audio.audio_analyzer import analyze_audio


# ---------------------------------
# Main pipeline
# ---------------------------------

def run_session():
    """
    Run the complete debate session pipeline.

    Pipeline:

        1. Create session
        2. Record audio
        3. Transcribe audio
        4. Analyze audio
        5. Complete session
    """

    print()
    print("==============================")
    print("      AI DEBATE COACH")
    print("==============================")


    # ---------------------------------
    # 1. Create session
    # ---------------------------------

    session_manager = SessionManager()

    session = session_manager.create_session()

    print()
    print(
        f"Starting session: "
        f"{session.session_id}"
    )


    # ---------------------------------
    # 2. Record audio
    # ---------------------------------

    session.start()

    audio_path = record_audio(
        session_directory=session.session_directory
    )

    session.finish_recording()


    # ---------------------------------
    # 3. Transcribe audio
    # ---------------------------------

    (
        transcription_path,
        transcript
    ) = transcribe_audio(
        audio_path=audio_path,
        session_id=session.session_id,
        session_directory=session.session_directory
    )

    session.finish_transcription()


    # ---------------------------------
    # 4. Analyze audio
    # ---------------------------------

    (
        analysis_path,
        analysis
    ) = analyze_audio(
        audio_path=audio_path,
        session_id=session.session_id,
        session_directory=session.session_directory
    )

    session.finish_analysis()


    # ---------------------------------
    # 5. Complete session
    # ---------------------------------

    session.complete()


    # ---------------------------------
    # Pipeline complete
    # ---------------------------------

    print()
    print("==============================")
    print("       SESSION COMPLETE")
    print("==============================")

    print()
    print(f"Session ID: {session.session_id}")
    print(f"Status: {session.status}")
    print(f"Session directory: {session.session_directory}")

    print()
    print("Files created:")

    print(
        f"  Recording:     "
        f"{session.audio_path}"
    )

    print(
        f"  Transcription: "
        f"{session.transcription_path}"
    )

    print(
        f"  Analysis:      "
        f"{session.analysis_path}"
    )

    print()


# ---------------------------------
# Program entry point
# ---------------------------------

if __name__ == "__main__":

    run_session()