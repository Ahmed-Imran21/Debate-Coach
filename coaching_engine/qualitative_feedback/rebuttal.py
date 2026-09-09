from typing import List

from ..models.feedback import FeedbackItem
from ..models.session import CoachingSession


def analyze_rebuttal(
    session: CoachingSession,
) -> List[FeedbackItem]:
    """
    Analyze the speaker's use of counterarguments, rebuttals,
    and concessions.

    This module relies on the semantic labels produced by the
    speech-content analysis.

    It evaluates:

        - counterarguments
        - rebuttals
        - concessions
        - reasoning used around rebuttals
        - evidence used around rebuttals

    The current speech-content representation does not explicitly
    define relationships such as:

        counterargument -> rebuttal
        rebuttal -> evidence
        rebuttal -> reasoning

    Therefore, this module evaluates the presence and general
    development of rebuttal-related content rather than claiming
    that a particular rebuttal successfully defeats a particular
    opposing argument.

    Returns:
        A list of FeedbackItem objects.
    """

    feedback: List[FeedbackItem] = []

    segments = session.speech_content.get("segments", [])

    if not segments:
        feedback.append(
            FeedbackItem(
                category="rebuttal",
                title="No rebuttal content available",
                issue="No semantic speech segments were available for analysis.",
                severity="high",
                evidence=[],
                explanation=(
                    "The coaching engine cannot evaluate rebuttal quality "
                    "because no semantic speech segments were provided."
                ),
                recommendation=(
                    "Make sure the speech-content analysis successfully "
                    "classified the speech before evaluating rebuttals."
                ),
            )
        )

        return feedback

    # ---------------------------------------------------------
    # Collect semantic segments
    # ---------------------------------------------------------

    counterarguments = [
        segment
        for segment in segments
        if "counterargument" in segment.get("labels", [])
    ]

    rebuttals = [
        segment
        for segment in segments
        if "rebuttal" in segment.get("labels", [])
    ]

    concessions = [
        segment
        for segment in segments
        if "concession" in segment.get("labels", [])
    ]

    reasoning = [
        segment
        for segment in segments
        if "reasoning" in segment.get("labels", [])
    ]

    evidence = [
        segment
        for segment in segments
        if "evidence" in segment.get("labels", [])
    ]

    # ---------------------------------------------------------
    # Counterarguments
    # ---------------------------------------------------------

    if counterarguments:
        feedback.append(
            FeedbackItem(
                category="rebuttal",
                title="Opposing arguments are identified",
                issue=(
                    f"{len(counterarguments)} counterargument segment(s) "
                    "were detected."
                ),
                severity="positive",
                evidence=[
                    segment.get("text", "")
                    for segment in counterarguments[:5]
                ],
                explanation=(
                    "Recognizing an opposing position is an important first "
                    "step in constructing an effective rebuttal."
                ),
                recommendation=(
                    "Continue identifying the strongest opposing arguments "
                    "before explaining why they are unconvincing."
                ),
                metadata={
                    "counterarguments": len(counterarguments),
                },
            )
        )
    else:
        feedback.append(
            FeedbackItem(
                category="rebuttal",
                title="No clear counterarguments detected",
                issue=(
                    "No segments were classified as counterarguments."
                ),
                severity="medium",
                evidence=[],
                explanation=(
                    "A rebuttal is stronger when it responds to a clearly "
                    "identified opposing position."
                ),
                recommendation=(
                    "Explicitly state the opposing argument before "
                    "explaining why it is weaker than your position."
                ),
                metadata={
                    "counterarguments": 0,
                },
            )
        )

    # ---------------------------------------------------------
    # Rebuttals
    # ---------------------------------------------------------

    if rebuttals:
        feedback.append(
            FeedbackItem(
                category="rebuttal",
                title="Rebuttals are present",
                issue=(
                    f"{len(rebuttals)} rebuttal segment(s) were detected."
                ),
                severity="positive",
                evidence=[
                    segment.get("text", "")
                    for segment in rebuttals[:5]
                ],
                explanation=(
                    "The speech contains explicit attempts to respond "
                    "to opposing arguments."
                ),
                recommendation=(
                    "Continue directly addressing opposing arguments "
                    "rather than simply repeating your own position."
                ),
                metadata={
                    "rebuttal_segments": len(rebuttals),
                },
            )
        )
    else:
        feedback.append(
            FeedbackItem(
                category="rebuttal",
                title="Limited rebuttal",
                issue="No rebuttal segments were detected.",
                severity="high",
                evidence=[],
                explanation=(
                    "Debate speeches are generally stronger when the speaker "
                    "actively responds to relevant opposing arguments."
                ),
                recommendation=(
                    "Identify an important opposing argument and explain "
                    "specifically why its reasoning or evidence is weaker."
                ),
                metadata={
                    "rebuttal_segments": 0,
                },
            )
        )

    # ---------------------------------------------------------
    # Counterargument + rebuttal
    # ---------------------------------------------------------

    if counterarguments and rebuttals:
        feedback.append(
            FeedbackItem(
                category="rebuttal",
                title="Opposing arguments are followed by rebuttals",
                issue=(
                    "Both counterarguments and rebuttals were detected "
                    "in the speech."
                ),
                severity="positive",
                evidence=[
                    f"Counterarguments: {len(counterarguments)}.",
                    f"Rebuttals: {len(rebuttals)}.",
                ],
                explanation=(
                    "The presence of both opposing arguments and rebuttals "
                    "suggests that the speech attempts to engage with "
                    "alternative positions."
                ),
                recommendation=(
                    "Make each rebuttal directly address the reasoning "
                    "or evidence presented by the opposing position."
                ),
                metadata={
                    "counterarguments": len(counterarguments),
                    "rebuttals": len(rebuttals),
                },
            )
        )

    # ---------------------------------------------------------
    # Rebuttal reasoning
    # ---------------------------------------------------------

    if rebuttals and reasoning:
        feedback.append(
            FeedbackItem(
                category="rebuttal",
                title="Rebuttals include reasoning",
                issue=(
                    "The speech contains both rebuttals and explicit "
                    "reasoning segments."
                ),
                severity="positive",
                evidence=[
                    f"Rebuttals: {len(rebuttals)}.",
                    f"Reasoning segments: {len(reasoning)}.",
                ],
                explanation=(
                    "A rebuttal is more convincing when the speaker "
                    "explains why the opposing position fails rather "
                    "than merely rejecting it."
                ),
                recommendation=(
                    "Keep explaining the specific logical reason why "
                    "an opposing argument does not undermine your position."
                ),
                metadata={
                    "rebuttals": len(rebuttals),
                    "reasoning": len(reasoning),
                },
            )
        )
    elif rebuttals and not reasoning:
        feedback.append(
            FeedbackItem(
                category="rebuttal",
                title="Rebuttals lack explicit reasoning",
                issue=(
                    "Rebuttals were detected, but no reasoning segments "
                    "were detected."
                ),
                severity="high",
                evidence=[
                    segment.get("text", "")
                    for segment in rebuttals[:5]
                ],
                explanation=(
                    "Simply rejecting an opposing argument does not show "
                    "the audience why that argument should be rejected."
                ),
                recommendation=(
                    "Explain the flaw, missing evidence, incorrect assumption, "
                    "or logical weakness in the opposing argument."
                ),
                metadata={
                    "rebuttals": len(rebuttals),
                    "reasoning": 0,
                },
            )
        )

    # ---------------------------------------------------------
    # Rebuttal evidence
    # ---------------------------------------------------------

    if rebuttals and evidence:
        feedback.append(
            FeedbackItem(
                category="rebuttal",
                title="Evidence is available to support rebuttals",
                issue=(
                    "The speech contains both rebuttals and evidence."
                ),
                severity="positive",
                evidence=[
                    f"Rebuttals: {len(rebuttals)}.",
                    f"Evidence segments: {len(evidence)}.",
                ],
                explanation=(
                    "Relevant evidence can strengthen a rebuttal by giving "
                    "the audience concrete support for rejecting an opposing claim."
                ),
                recommendation=(
                    "Use the most relevant evidence directly when explaining "
                    "why an opposing claim is inaccurate or insufficient."
                ),
                metadata={
                    "rebuttals": len(rebuttals),
                    "evidence": len(evidence),
                },
            )
        )
    elif rebuttals and not evidence:
        feedback.append(
            FeedbackItem(
                category="rebuttal",
                title="Rebuttals lack detected evidence",
                issue=(
                    "Rebuttals were detected, but no evidence segments "
                    "were detected."
                ),
                severity="medium",
                evidence=[],
                explanation=(
                    "Some rebuttals may be stronger when they are supported "
                    "by relevant facts or evidence."
                ),
                recommendation=(
                    "Where appropriate, support rebuttals with specific "
                    "evidence rather than relying entirely on assertion."
                ),
                metadata={
                    "rebuttals": len(rebuttals),
                    "evidence": 0,
                },
            )
        )

    # ---------------------------------------------------------
    # Concessions
    # ---------------------------------------------------------

    if concessions:
        feedback.append(
            FeedbackItem(
                category="rebuttal",
                title="Concessions are used",
                issue=(
                    f"{len(concessions)} concession segment(s) were detected."
                ),
                severity="positive",
                evidence=[
                    segment.get("text", "")
                    for segment in concessions[:5]
                ],
                explanation=(
                    "Acknowledging a valid part of an opposing argument "
                    "can make a rebuttal more credible and demonstrate "
                    "that the speaker has considered the opposing position."
                ),
                recommendation=(
                    "When appropriate, acknowledge a valid opposing point "
                    "and then explain why your overall position still stands."
                ),
                metadata={
                    "concessions": len(concessions),
                },
            )
        )

    # ---------------------------------------------------------
    # Rebuttal balance
    # ---------------------------------------------------------

    if rebuttals and not counterarguments:
        feedback.append(
            FeedbackItem(
                category="rebuttal",
                title="Rebuttals lack clearly identified targets",
                issue=(
                    "Rebuttals were detected, but no counterarguments "
                    "were explicitly identified."
                ),
                severity="medium",
                evidence=[
                    segment.get("text", "")
                    for segment in rebuttals[:5]
                ],
                explanation=(
                    "The current semantic analysis cannot establish whether "
                    "these rebuttals directly respond to a specific opposing "
                    "argument."
                ),
                recommendation=(
                    "Clearly state the opposing argument before rebutting it "
                    "so the audience can follow exactly what you are responding to."
                ),
                metadata={
                    "rebuttals": len(rebuttals),
                    "counterarguments": 0,
                },
            )
        )

    # ---------------------------------------------------------
    # Overall rebuttal development
    # ---------------------------------------------------------

    if counterarguments and rebuttals and (reasoning or evidence):
        feedback.append(
            FeedbackItem(
                category="rebuttal",
                title="Well-developed rebuttal structure",
                issue=(
                    "The speech contains opposing arguments, rebuttals, "
                    "and supporting reasoning or evidence."
                ),
                severity="positive",
                evidence=[
                    f"Counterarguments: {len(counterarguments)}.",
                    f"Rebuttals: {len(rebuttals)}.",
                    f"Reasoning: {len(reasoning)}.",
                    f"Evidence: {len(evidence)}.",
                ],
                explanation=(
                    "The speech demonstrates several components of a "
                    "developed rebuttal: identifying an opposing position, "
                    "responding to it, and providing support for the response."
                ),
                recommendation=(
                    "Maintain this structure and make the connection between "
                    "the opposing claim, your rebuttal, and your supporting "
                    "reasoning explicit."
                ),
                metadata={
                    "counterarguments": len(counterarguments),
                    "rebuttals": len(rebuttals),
                    "reasoning": len(reasoning),
                    "evidence": len(evidence),
                },
            )
        )

    return feedback