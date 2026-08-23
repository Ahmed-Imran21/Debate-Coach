from pathlib import Path

from audio.recorder import record_audio
from transcription.transcriber import transcribe_audio


# -----------------------------
# Configuration
# -----------------------------

RECORDINGS_DIRECTORY = Path(
    "audio/recordings"
)

TRANSCRIPTS_DIRECTORY = Path(
    "transcription/transcripts"
)


# -----------------------------
# Main pipeline
# -----------------------------

def run_debate_session():

    print()
    print("=" * 50)
    print("           AI DEBATE COACH")
    print("=" * 50)

    # -------------------------
    # Step 1: Record audio
    # -------------------------

    print()
    print("STEP 1: RECORDING")
    print("-" * 50)

    session_id, audio_path = record_audio(
        output_directory=RECORDINGS_DIRECTORY
    )

    # -------------------------
    # Step 2: Transcribe audio
    # -------------------------

    print()
    print("STEP 2: TRANSCRIPTION")
    print("-" * 50)

    session_id, transcript_path, transcript = transcribe_audio(
        audio_path=audio_path,
        session_id=session_id,
        output_directory=TRANSCRIPTS_DIRECTORY
    )

    # -------------------------
    # Step 3: Session complete
    # -------------------------

    print()
    print("=" * 50)
    print("           SESSION COMPLETE")
    print("=" * 50)

    print()
    print(f"Session ID:       {session_id}")
    print(f"Audio file:       {audio_path}")
    print(f"Transcript file:  {transcript_path}")
    print()


# -----------------------------
# Program entry point
# -----------------------------

if __name__ == "__main__":
    run_debate_session()