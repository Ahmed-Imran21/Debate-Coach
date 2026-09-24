from typing import List

from .models.feedback import FeedbackItem
from .models.session import CoachingSession


def analyze_quantitative_feedback(
    session: CoachingSession,
) -> List[FeedbackItem]:
    """
    Analyze objective speech metrics and generate quantitative
    coaching feedback.

    This analysis is deterministic and does not use an LLM.
    """

    feedback: List[FeedbackItem] = []

    speech = session.raw_metrics.get("speech", {})
    pauses = session.raw_metrics.get("pauses", {})
    fillers = session.raw_metrics.get("fillers", {})
    stutters = session.raw_metrics.get("stutters", {})

    # ---------------------------------------------------------
    # Speaking pace
    # ---------------------------------------------------------

    wpm = speech.get("words_per_minute")

    if wpm is not None:

        if wpm > 180:
            feedback.append(
                FeedbackItem(
                    category="quantitative",
                    title="Speaking pace is too fast",
                    issue="Your speaking rate is above the recommended range.",
                    severity="high",
                    evidence=[
                        f"Speaking rate: {wpm:.2f} words per minute."
                    ],
                    explanation=(
                        "A very fast speaking pace can make arguments harder "
                        "to follow and can reduce the impact of important points."
                    ),
                    recommendation=(
                        "Slow down, especially when introducing a new argument "
                        "or explaining important evidence."
                    ),
                    metadata={
                        "metric": "words_per_minute",
                        "value": wpm,
                    },
                )
            )

        elif wpm < 110:
            feedback.append(
                FeedbackItem(
                    category="quantitative",
                    title="Speaking pace is too slow",
                    issue="Your speaking rate is below the recommended range.",
                    severity="medium",
                    evidence=[
                        f"Speaking rate: {wpm:.2f} words per minute."
                    ],
                    explanation=(
                        "A very slow pace can reduce energy and make the "
                        "speech feel less engaging."
                    ),
                    recommendation=(
                        "Increase your pace slightly while maintaining clear "
                        "pronunciation and deliberate pauses."
                    ),
                    metadata={
                        "metric": "words_per_minute",
                        "value": wpm,
                    },
                )
            )

        else:
            feedback.append(
                FeedbackItem(
                    category="quantitative",
                    title="Speaking pace is within range",
                    issue="Your speaking rate is within the target range.",
                    severity="positive",
                    evidence=[
                        f"Speaking rate: {wpm:.2f} words per minute."
                    ],
                    explanation=(
                        "Your overall speaking pace is appropriate for "
                        "delivering a debate argument."
                    ),
                    recommendation=(
                        "Maintain this general pace while varying it naturally "
                        "for emphasis."
                    ),
                    metadata={
                        "metric": "words_per_minute",
                        "value": wpm,
                    },
                )
            )

    # ---------------------------------------------------------
    # Speech percentage
    # ---------------------------------------------------------

    speech_percentage = speech.get("speech_percentage")

    if speech_percentage is not None:

        if speech_percentage > 95:
            feedback.append(
                FeedbackItem(
                    category="quantitative",
                    title="Very little silence",
                    issue="You spent almost the entire session speaking.",
                    severity="medium",
                    evidence=[
                        f"Speech percentage: {speech_percentage:.2f}%."
                    ],
                    explanation=(
                        "Having almost no silence can make a speech sound "
                        "rushed and leaves little room for deliberate emphasis."
                    ),
                    recommendation=(
                        "Introduce short intentional pauses between major "
                        "ideas and before important conclusions."
                    ),
                    metadata={
                        "metric": "speech_percentage",
                        "value": speech_percentage,
                    },
                )
            )

        elif speech_percentage < 60:
            feedback.append(
                FeedbackItem(
                    category="quantitative",
                    title="Large amount of silence",
                    issue="A significant portion of the session contained silence.",
                    severity="medium",
                    evidence=[
                        f"Speech percentage: {speech_percentage:.2f}%."
                    ],
                    explanation=(
                        "Extended periods of silence can interrupt the flow "
                        "of your argument and reduce perceived confidence."
                    ),
                    recommendation=(
                        "Reduce unnecessary gaps while keeping short pauses "
                        "where they improve emphasis or clarity."
                    ),
                    metadata={
                        "metric": "speech_percentage",
                        "value": speech_percentage,
                    },
                )
            )

    # ---------------------------------------------------------
    # Pauses
    # ---------------------------------------------------------

    pause_count = pauses.get("count", 0)
    longest_pause = pauses.get("longest_duration", 0)

    if pause_count == 0:
        feedback.append(
            FeedbackItem(
                category="quantitative",
                title="No detected pauses",
                issue="No pauses were detected in the speech.",
                severity="medium",
                evidence=[
                    "Detected pauses: 0."
                ],
                explanation=(
                    "Pauses can help separate ideas, emphasize important "
                    "points, and give the audience time to process an argument."
                ),
                recommendation=(
                    "Consider adding deliberate pauses between major arguments "
                    "and before important conclusions."
                ),
                metadata={
                    "metric": "pause_count",
                    "value": pause_count,
                },
            )
        )

    elif longest_pause >= 3:
        feedback.append(
            FeedbackItem(
                category="quantitative",
                title="Long pause detected",
                issue="At least one unusually long pause occurred.",
                severity="medium",
                evidence=[
                    f"Longest pause: {longest_pause:.2f} seconds.",
                    f"Total pauses: {pause_count}.",
                ],
                explanation=(
                    "Long pauses can interrupt the flow of an argument, "
                    "particularly when they occur unexpectedly."
                ),
                recommendation=(
                    "Practice transitions between arguments so you can move "
                    "smoothly from one point to the next."
                ),
                metadata={
                    "metric": "longest_pause",
                    "value": longest_pause,
                    "pause_count": pause_count,
                },
            )
        )

    # ---------------------------------------------------------
    # Fillers
    # ---------------------------------------------------------

    filler_count = fillers.get("count", 0)

    if filler_count > 0:

        filler_words = fillers.get("words", {})

        feedback.append(
            FeedbackItem(
                category="quantitative",
                title="Filler words detected",
                issue="Filler words were used during the speech.",
                severity="medium" if filler_count < 5 else "high",
                evidence=[
                    f"Filler instances: {filler_count}.",
                    f"Filler words: {filler_words}",
                ],
                explanation=(
                    "Frequent filler words can make a speaker sound less "
                    "confident and can distract from the argument."
                ),
                recommendation=(
                    "Replace filler words with short intentional pauses when "
                    "you need time to think."
                ),
                metadata={
                    "metric": "filler_count",
                    "value": filler_count,
                    "words": filler_words,
                },
            )
        )

    else:
        feedback.append(
            FeedbackItem(
                category="quantitative",
                title="No filler words detected",
                issue="No filler words were detected.",
                severity="positive",
                evidence=[
                    "Filler instances: 0."
                ],
                explanation=(
                    "Your speech did not contain detectable filler words."
                ),
                recommendation=(
                    "Maintain this habit and continue using deliberate pauses "
                    "instead of verbal fillers."
                ),
                metadata={
                    "metric": "filler_count",
                    "value": filler_count,
                },
            )
        )

    # ---------------------------------------------------------
    # Stutters
    # ---------------------------------------------------------

    stutter_count = stutters.get("count", 0)

    if stutter_count > 0:

        feedback.append(
            FeedbackItem(
                category="quantitative",
                title="Speech repetitions detected",
                issue=(
                    "Potential stuttering or repeated speech patterns "
                    "were detected."
                ),
                severity="medium" if stutter_count < 5 else "high",
                evidence=[
                    f"Detected instances: {stutter_count}."
                ],
                explanation=(
                    "Repeated or interrupted speech can affect fluency and "
                    "make some parts of an argument harder to follow."
                ),
                recommendation=(
                    "Practice difficult transitions and key phrases slowly, "
                    "then gradually increase your speaking pace."
                ),
                metadata={
                    "metric": "stutter_count",
                    "value": stutter_count,
                },
            )
        )

    else:
        feedback.append(
            FeedbackItem(
                category="quantitative",
                title="No stuttering detected",
                issue="No detectable stuttering instances were found.",
                severity="positive",
                evidence=[
                    "Detected instances: 0."
                ],
                explanation=(
                    "The speech analysis did not identify detectable "
                    "stuttering patterns."
                ),
                recommendation=(
                    "Maintain clear and controlled delivery."
                ),
                metadata={
                    "metric": "stutter_count",
                    "value": stutter_count,
                },
            )
        )

    return feedback