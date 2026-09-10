from session_manager import SessionManager

from coaching_engine.engine import CoachingEngine

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
        7. Run coaching engine
        8. Complete session
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
    # 7. Run Coaching Engine
    # -----------------------------------------------------

    print("\nStarting coaching analysis...")

    coaching_engine = CoachingEngine(
        sessions_dir="sessions"
    )

    feedback, scores = coaching_engine.analyze_session(
        session_id=session.session_id
    )

    print("\nCoaching analysis completed.")

    # -----------------------------------------------------
    # Display coaching scores
    # -----------------------------------------------------

    print("\n========================================")
    print("COACHING SCORES")
    print("========================================")

    print(
        f"Quantitative:   "
        f"{scores.categories.quantitative:.2f}"
    )

    print(
        f"Argumentation:  "
        f"{scores.categories.argumentation:.2f}"
    )

    print(
        f"Rebuttal:       "
        f"{scores.categories.rebuttal:.2f}"
    )

    print(
        f"Structure:      "
        f"{scores.categories.structure:.2f}"
    )

    print(
        f"Persuasion:     "
        f"{scores.categories.persuasion:.2f}"
    )

    print(
        f"Logic:          "
        f"{scores.categories.logic:.2f}"
    )

    print("----------------------------------------")

    print(
        f"Overall:        "
        f"{scores.overall:.2f}"
    )

    # -----------------------------------------------------
    # Display coaching feedback
    # -----------------------------------------------------

    print("\n========================================")
    print("COACHING FEEDBACK")
    print("========================================")

    if not feedback:
        print("\nNo coaching feedback generated.")

    else:
        for item in feedback:

            print(
                f"\n[{item.severity.upper()}] "
                f"{item.title}"
            )

            print(
                f"Category: {item.category}"
            )

            print(
                f"Issue: {item.issue}"
            )

            if item.evidence:
                print("Evidence:")

                for evidence in item.evidence:
                    print(
                        f"  - {evidence}"
                    )

            if item.explanation:
                print(
                    f"Explanation: "
                    f"{item.explanation}"
                )

            if item.recommendation:
                print(
                    f"Recommendation: "
                    f"{item.recommendation}"
                )

    # -----------------------------------------------------
    # 8. Complete session
    # -----------------------------------------------------

    session.complete()

    print("\n========================================")
    print("SESSION COMPLETED")
    print("========================================")

    print(
        f"Session ID:        "
        f"{session.session_id}"
    )

    print(
        f"Session directory: "
        f"{session.session_directory}"
    )

    print(
        f"Audio:             "
        f"{session.audio_path}"
    )

    print(
        f"Transcription:     "
        f"{session.transcription_path}"
    )

    print(
        f"Audio analysis:    "
        f"{session.analysis_path}"
    )

    print(
        f"Raw metrics:       "
        f"{raw_metrics_path}"
    )

    print(
        f"Speech content:    "
        f"{speech_content_path}"
    )

    print(
        f"Overall score:     "
        f"{scores.overall:.2f}"
    )

    print("========================================\n")


if __name__ == "__main__":
    run_session()
