from session_manager import SessionManager

from audio.recorder import record_audio
from audio.transcriber import transcribe_audio
from audio.audio_analyzer import analyze_audio

from raw_metrics.metrics import analyze_metrics

from speech_analysis.speech_analyzer import analyze_speech


def run_session():
    """
    Run a complete Debate Coach session.

    Pipeline:
        1. Create session
        2. Record audio
        3. Transcribe audio
        4. Analyze audio
        5. Calculate raw speech metrics
        6. Analyze semantic speech content
        7. Complete session
    """

    # -----------------------------------------------------
    # 1. Create session
    # -----------------------------------------------------

    manager = SessionManager()

    session = manager.create_session()

    print(f"\nSession created: {session.session_id}")
    print(f"Session directory: {session.session_directory}")

    session.start()

    # -----------------------------------------------------
    # 2. Record audio
    # -----------------------------------------------------

    print("\nStarting recording...")

    record_audio(
        session.session_directory
    )

    session.finish_recording()

    print(f"Recording saved to: {session.audio_path}")

    # -----------------------------------------------------
    # 3. Transcribe audio
    # -----------------------------------------------------

    print("\nTranscribing audio...")

    transcription_path, transcription = transcribe_audio(
        session.audio_path,
        session.session_id,
        session.session_directory
    )

    session.finish_transcription()

    print(f"Transcription saved to: {transcription_path}")

    # -----------------------------------------------------
    # 4. Analyze audio
    # -----------------------------------------------------

    print("\nAnalyzing audio...")

    analysis_path, analysis = analyze_audio(
        session.audio_path,
        session.session_id,
        session.session_directory
    )

    session.finish_analysis()

    print(f"Audio analysis saved to: {analysis_path}")

    # -----------------------------------------------------
    # 5. Calculate raw speech metrics
    # -----------------------------------------------------

    print("\nCalculating raw speech metrics...")

    raw_metrics_path, raw_metrics = analyze_metrics(
        session.session_id,
        session.session_directory
    )

    print(f"Raw metrics saved to: {raw_metrics_path}")

    # -----------------------------------------------------
    # 6. Analyze semantic speech content
    # -----------------------------------------------------

    print("\nAnalyzing speech content...")

    speech_content_path, speech_content = analyze_speech(
        session.session_id,
        session.session_directory
    )

    print(f"Speech content saved to: {speech_content_path}")

    # -----------------------------------------------------
    # 7. Complete session
    # -----------------------------------------------------

    session.complete()

    print("\n========================================")
    print("SESSION COMPLETED")
    print("========================================")
    print(f"Session ID:        {session.session_id}")
    print(f"Session directory: {session.session_directory}")
    print(f"Audio:             {session.audio_path}")
    print(f"Transcription:     {session.transcription_path}")
    print(f"Audio analysis:    {session.analysis_path}")
    print(f"Raw metrics:       {raw_metrics_path}")
    print(f"Speech content:    {speech_content_path}")
    print("========================================\n")


if __name__ == "__main__":
    run_session()