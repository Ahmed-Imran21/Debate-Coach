import traceback

from session import Session

from audio.transcriber import transcribe_audio
from audio.audio_analyzer import analyze_audio

from raw_metrics.metrics import analyze_metrics

from speech_analysis.speech_analyzer import analyze_speech

from coaching_engine.engine import CoachingEngine
from coaching_engine.utils.result_writer import (
    save_coaching_results,
)


def run_session_pipeline(
    session: Session,
    api_client,
) -> None:
    """
    Run the full analysis pipeline for one session.

    The same process-wide APIClient is shared by all sessions.

    It contains:

        - shared LLM API scheduler
        - shared LLM request queue
        - shared LLM key pool
        - shared WhisperClient
        - shared Whisper queue
        - shared Whisper key pool
    """

    try:

        _run(
            session,
            api_client,
        )

    except Exception as error:

        session.mark_failed(
            error=(
                f"{type(error).__name__}: "
                f"{error}"
            )
        )

        print(
            f"\n[session "
            f"{session.session_id}] "
            f"pipeline failed:\n"
            f"{traceback.format_exc()}"
        )


def _run(
    session: Session,
    api_client,
) -> None:

    def on_queued(
        estimated_wait_seconds: float,
    ) -> None:

        session.mark_waiting_for_capacity(
            estimated_wait_seconds
        )

    # =========================================================
    # 1. TRANSCRIBE
    # =========================================================

    session.mark_transcribing()

    transcription_path, transcription = (
        transcribe_audio(
            audio_path=session.audio_path,
            session_id=session.session_id,
            session_directory=(
                session.session_directory
            ),
            whisper_client=(
                api_client.whisper_client
            ),
        )
    )

    session.finish_transcription()

    # =========================================================
    # 2. AUDIO ANALYSIS
    # =========================================================

    session.mark_analyzing_audio()

    analyze_audio(
        audio_path=session.audio_path,
        session_id=session.session_id,
        session_directory=(
            session.session_directory
        ),
    )

    session.finish_analysis()

    # =========================================================
    # 3. RAW DETERMINISTIC METRICS
    # =========================================================

    session.mark_calculating_metrics()

    analyze_metrics(
        session_id=session.session_id,
        session_directory=(
            session.session_directory
        ),
    )

    session.mark_metrics_calculated()

    # =========================================================
    # 4. SEMANTIC SPEECH ANALYSIS
    # =========================================================

    session.mark_analyzing_speech()

    analyze_speech(
        session_id=session.session_id,
        session_directory=(
            session.session_directory
        ),
        api_client=api_client,
        on_queued=on_queued,
    )

    session.mark_speech_analyzed()

    # =========================================================
    # 5. COACHING ANALYSIS
    # =========================================================

    session.mark_coaching()

    coaching_engine = CoachingEngine(
        sessions_dir=str(
            session.base_directory
        ),
        api_client=api_client,
        on_queued=on_queued,
    )

    feedback, scores = (
        coaching_engine.analyze_session(
            session_id=session.session_id
        )
    )

    save_coaching_results(
        session_id=session.session_id,
        feedback=feedback,
        scores=scores,
        sessions_dir=str(
            session.base_directory
        ),
    )

    # =========================================================
    # 6. DONE
    # =========================================================

    session.complete()