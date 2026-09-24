from typing import List

from ..models.feedback import FeedbackItem
from ..models.session import CoachingSession


def analyze_argumentation(
    session: CoachingSession,
) -> List[FeedbackItem]:
    """
    Analyze the speaker's argumentation using the semantic
    information contained in speech_content.json.

    This module does not independently determine whether an
    argument is logically valid or persuasive. It uses the
    semantic labels already produced by the speech-content
    analysis to identify patterns such as:

        - presence of arguments
        - claims without supporting reasoning
        - claims without evidence
        - arguments supported by reasoning
        - use of examples
        - unsupported claims
        - overall argument development

    Returns:
        A list of FeedbackItem objects.
    """

    feedback: List[FeedbackItem] = []

    segments = session.speech_content.get("segments", [])

    if not segments:
        feedback.append(
            FeedbackItem(
                category="argumentation",
                title="No argumentation detected",
                issue="No semantic speech segments were available for analysis.",
                severity="high",
                evidence=[],
                explanation=(
                    "The coaching engine could not identify the speaker's "
                    "arguments because no semantic segments were provided."
                ),
                recommendation=(
                    "Make sure the speech-content analysis successfully "
                    "classified the speech before evaluating argumentation."
                ),
            )
        )

        return feedback

    # ---------------------------------------------------------
    # Collect semantic segments
    # ---------------------------------------------------------

    claims = [
        segment
        for segment in segments
        if "claim" in segment.get("labels", [])
    ]

    arguments = [
        segment
        for segment in segments
        if "argument" in segment.get("labels", [])
    ]

    evidence = [
        segment
        for segment in segments
        if "evidence" in segment.get("labels", [])
    ]

    examples = [
        segment
        for segment in segments
        if "example" in segment.get("labels", [])
    ]

    reasoning = [
        segment
        for segment in segments
        if "reasoning" in segment.get("labels", [])
    ]

    conclusions = [
        segment
        for segment in segments
        if "conclusion" in segment.get("labels", [])
    ]

    # ---------------------------------------------------------
    # No arguments / claims
    # ---------------------------------------------------------

    if not claims and not arguments:
        feedback.append(
            FeedbackItem(
                category="argumentation",
                title="Few clear arguments detected",
                issue=(
                    "The speech contains no segments explicitly classified "
                    "as claims or arguments."
                ),
                severity="high",
                evidence=[],
                explanation=(
                    "A debate speech needs clearly identifiable positions "
                    "that can be supported and defended."
                ),
                recommendation=(
                    "State your main claim clearly and then develop it with "
                    "reasoning and supporting evidence."
                ),
            )
        )

        return feedback

    # ---------------------------------------------------------
    # Argumentation presence
    # ---------------------------------------------------------

    feedback.append(
        FeedbackItem(
            category="argumentation",
            title="Arguments identified",
            issue=(
                f"The speech contains {len(claims)} claim(s) and "
                f"{len(arguments)} argument segment(s)."
            ),
            severity="positive",
            evidence=[
                f"Claims detected: {len(claims)}.",
                f"Arguments detected: {len(arguments)}.",
            ],
            explanation=(
                "The speech contains identifiable argumentative content "
                "rather than consisting entirely of unrelated statements."
            ),
            recommendation=(
                "Continue making your main positions explicit and "
                "developing each one with supporting reasoning."
            ),
            metadata={
                "claims": len(claims),
                "arguments": len(arguments),
            },
        )
    )

    # ---------------------------------------------------------
    # Reasoning support
    # ---------------------------------------------------------

    if reasoning:
        feedback.append(
            FeedbackItem(
                category="argumentation",
                title="Reasoning is present",
                issue=(
                    f"{len(reasoning)} segment(s) were classified as reasoning."
                ),
                severity="positive",
                evidence=[
                    segment.get("text", "")
                    for segment in reasoning[:5]
                ],
                explanation=(
                    "The speech contains explicit reasoning that helps "
                    "explain why the speaker's claims should be accepted."
                ),
                recommendation=(
                    "Continue explaining why your claims are true instead "
                    "of relying only on assertions."
                ),
                metadata={
                    "reasoning_segments": len(reasoning),
                },
            )
        )

    else:
        feedback.append(
            FeedbackItem(
                category="argumentation",
                title="Limited explicit reasoning",
                issue=(
                    "No segments were classified as reasoning."
                ),
                severity="high",
                evidence=[],
                explanation=(
                    "Claims are stronger when the speaker explains the "
                    "reasoning that connects the claim to its support."
                ),
                recommendation=(
                    "After stating a claim, explicitly explain why it "
                    "follows from the facts or principles you provide."
                ),
                metadata={
                    "reasoning_segments": 0,
                },
            )
        )

    # ---------------------------------------------------------
    # Evidence support
    # ---------------------------------------------------------

    if evidence:
        feedback.append(
            FeedbackItem(
                category="argumentation",
                title="Supporting evidence is present",
                issue=(
                    f"{len(evidence)} segment(s) were classified as evidence."
                ),
                severity="positive",
                evidence=[
                    segment.get("text", "")
                    for segment in evidence[:5]
                ],
                explanation=(
                    "The speech uses identifiable evidence to support "
                    "its argumentative content."
                ),
                recommendation=(
                    "Continue supporting important claims with specific, "
                    "relevant evidence."
                ),
                metadata={
                    "evidence_segments": len(evidence),
                },
            )
        )

    else:
        feedback.append(
            FeedbackItem(
                category="argumentation",
                title="No supporting evidence detected",
                issue=(
                    "No segments were classified as evidence."
                ),
                severity="high",
                evidence=[],
                explanation=(
                    "Arguments that rely only on assertions can be less "
                    "convincing because the audience has little concrete "
                    "support for the claims."
                ),
                recommendation=(
                    "Support important claims with facts, statistics, "
                    "examples, observations, or other relevant evidence."
                ),
                metadata={
                    "evidence_segments": 0,
                },
            )
        )

    # ---------------------------------------------------------
    # Examples
    # ---------------------------------------------------------

    if examples:
        feedback.append(
            FeedbackItem(
                category="argumentation",
                title="Examples are used",
                issue=(
                    f"{len(examples)} segment(s) were classified as examples."
                ),
                severity="positive",
                evidence=[
                    segment.get("text", "")
                    for segment in examples[:5]
                ],
                explanation=(
                    "Examples can make abstract arguments easier for an "
                    "audience to understand."
                ),
                recommendation=(
                    "Use examples selectively to clarify important "
                    "arguments without replacing stronger evidence."
                ),
                metadata={
                    "example_segments": len(examples),
                },
            )
        )

    # ---------------------------------------------------------
    # Claims without obvious support
    # ---------------------------------------------------------
    #
    # The current speech-content representation does not explicitly
    # contain relationships such as:
    #
    #     claim -> evidence
    #     claim -> reasoning
    #
    # Therefore we cannot reliably determine which specific claim
    # is unsupported. We can only identify the broader pattern when
    # claims exist but no reasoning/evidence exists.
    # ---------------------------------------------------------

    if claims and not reasoning and not evidence:
        feedback.append(
            FeedbackItem(
                category="argumentation",
                title="Claims lack visible support",
                issue=(
                    "Claims were detected, but no reasoning or evidence "
                    "was detected alongside them."
                ),
                severity="high",
                evidence=[
                    segment.get("text", "")
                    for segment in claims[:5]
                ],
                explanation=(
                    "A claim becomes more persuasive when the speaker "
                    "explains why it is true and provides support for it."
                ),
                recommendation=(
                    "For each major claim, provide both a clear explanation "
                    "of why it is true and concrete support where appropriate."
                ),
                metadata={
                    "claims": len(claims),
                    "reasoning": len(reasoning),
                    "evidence": len(evidence),
                },
            )
        )

    # ---------------------------------------------------------
    # Arguments with both reasoning and evidence
    # ---------------------------------------------------------

    if arguments and reasoning and evidence:
        feedback.append(
            FeedbackItem(
                category="argumentation",
                title="Arguments have multiple forms of support",
                issue=(
                    "The speech contains arguments together with both "
                    "reasoning and evidence."
                ),
                severity="positive",
                evidence=[
                    f"Arguments: {len(arguments)}.",
                    f"Reasoning segments: {len(reasoning)}.",
                    f"Evidence segments: {len(evidence)}.",
                ],
                explanation=(
                    "Combining reasoning with evidence can make an argument "
                    "more developed and easier to defend."
                ),
                recommendation=(
                    "Maintain the pattern of stating the claim, explaining "
                    "the reasoning, and then providing relevant support."
                ),
                metadata={
                    "arguments": len(arguments),
                    "reasoning": len(reasoning),
                    "evidence": len(evidence),
                },
            )
        )

    # ---------------------------------------------------------
    # Conclusions
    # ---------------------------------------------------------

    if conclusions:
        feedback.append(
            FeedbackItem(
                category="argumentation",
                title="Conclusions are present",
                issue=(
                    f"{len(conclusions)} segment(s) were classified "
                    "as conclusions."
                ),
                severity="positive",
                evidence=[
                    segment.get("text", "")
                    for segment in conclusions[:5]
                ],
                explanation=(
                    "Explicit conclusions can help make the intended "
                    "result of an argument clear to the audience."
                ),
                recommendation=(
                    "Use conclusions to clearly connect your reasoning "
                    "back to the claim you are defending."
                ),
                metadata={
                    "conclusion_segments": len(conclusions),
                },
            )
        )

    return feedback