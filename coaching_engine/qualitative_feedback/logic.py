from typing import List

from ..models.feedback import FeedbackItem
from ..models.session import CoachingSession


def analyze_logic(
    session: CoachingSession,
) -> List[FeedbackItem]:
    """
    Analyze the logical characteristics of a debate speech.

    This module uses the semantic labels produced by the speech-content
    analysis. It focuses on:

        - presence of reasoning
        - claims supported by reasoning/evidence
        - logical fallacies detected by the semantic analysis
        - counterarguments and rebuttals
        - conclusions
        - overall logical development

    The current speech-content representation does not explicitly encode
    relationships such as:

        claim -> reasoning
        claim -> evidence
        claim -> conclusion

    Therefore, this module does not claim to prove that a particular
    claim is logically valid or invalid. It evaluates the logical
    structures that are available in the semantic analysis.

    Returns:
        A list of FeedbackItem objects.
    """

    feedback: List[FeedbackItem] = []

    segments = session.speech_content.get("segments", [])

    if not segments:
        feedback.append(
            FeedbackItem(
                category="logic",
                title="No logical content available",
                issue="No semantic speech segments were available for analysis.",
                severity="high",
                evidence=[],
                explanation=(
                    "The coaching engine cannot evaluate logical structure "
                    "because no semantic speech segments were provided."
                ),
                recommendation=(
                    "Make sure the speech-content analysis successfully "
                    "classified the speech before evaluating logic."
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

    rebuttals = [
        segment
        for segment in segments
        if "rebuttal" in segment.get("labels", [])
    ]

    counterarguments = [
        segment
        for segment in segments
        if "counterargument" in segment.get("labels", [])
    ]

    conclusions = [
        segment
        for segment in segments
        if "conclusion" in segment.get("labels", [])
    ]

    fallacies = [
        segment
        for segment in segments
        if "logical_fallacy" in segment.get("labels", [])
    ]

    # ---------------------------------------------------------
    # Logical foundation
    # ---------------------------------------------------------

    if claims or arguments:
        feedback.append(
            FeedbackItem(
                category="logic",
                title="Logical positions are identifiable",
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
                    "Logical evaluation is easier when the speaker's "
                    "positions and arguments are clearly identifiable."
                ),
                recommendation=(
                    "Continue stating claims clearly before explaining "
                    "the reasoning that supports them."
                ),
                metadata={
                    "claims": len(claims),
                    "arguments": len(arguments),
                },
            )
        )
    else:
        feedback.append(
            FeedbackItem(
                category="logic",
                title="Weak logical structure",
                issue="No clear claims or arguments were detected.",
                severity="high",
                evidence=[],
                explanation=(
                    "A logically developed debate speech needs identifiable "
                    "positions that can be supported and evaluated."
                ),
                recommendation=(
                    "State your main claim clearly and develop it with "
                    "explicit reasons and supporting evidence."
                ),
                metadata={
                    "claims": len(claims),
                    "arguments": len(arguments),
                },
            )
        )

    # ---------------------------------------------------------
    # Reasoning
    # ---------------------------------------------------------

    if reasoning:
        feedback.append(
            FeedbackItem(
                category="logic",
                title="Explicit reasoning is present",
                issue=(
                    f"{len(reasoning)} reasoning segment(s) were detected."
                ),
                severity="positive",
                evidence=[
                    segment.get("text", "")
                    for segment in reasoning[:5]
                ],
                explanation=(
                    "The speech contains explicit reasoning that explains "
                    "why particular claims or conclusions should follow."
                ),
                recommendation=(
                    "Continue making the reasoning between your points "
                    "explicit rather than leaving connections for the "
                    "audience to infer."
                ),
                metadata={
                    "reasoning_segments": len(reasoning),
                },
            )
        )
    else:
        feedback.append(
            FeedbackItem(
                category="logic",
                title="Limited explicit reasoning",
                issue="No reasoning segments were detected.",
                severity="high",
                evidence=[],
                explanation=(
                    "Without explicit reasoning, claims can appear "
                    "unsupported even when the speaker has relevant evidence."
                ),
                recommendation=(
                    "Explain why each major piece of evidence supports "
                    "your claim and make the logical connection explicit."
                ),
                metadata={
                    "reasoning_segments": 0,
                },
            )
        )

    # ---------------------------------------------------------
    # Evidence and logical support
    # ---------------------------------------------------------

    if evidence and reasoning:
        feedback.append(
            FeedbackItem(
                category="logic",
                title="Reasoning and evidence are combined",
                issue=(
                    "The speech contains both reasoning and supporting evidence."
                ),
                severity="positive",
                evidence=[
                    f"Reasoning segments: {len(reasoning)}.",
                    f"Evidence segments: {len(evidence)}.",
                ],
                explanation=(
                    "Combining evidence with an explanation of how that "
                    "evidence supports a claim creates a stronger logical "
                    "structure than relying on either alone."
                ),
                recommendation=(
                    "Maintain the pattern of presenting relevant evidence "
                    "and explicitly explaining its connection to your claim."
                ),
                metadata={
                    "reasoning_segments": len(reasoning),
                    "evidence_segments": len(evidence),
                },
            )
        )
    elif not evidence:
        feedback.append(
            FeedbackItem(
                category="logic",
                title="Limited supporting evidence",
                issue="No evidence segments were detected.",
                severity="medium",
                evidence=[],
                explanation=(
                    "Logical reasoning is stronger when important premises "
                    "are supported by relevant evidence."
                ),
                recommendation=(
                    "Support important factual claims with relevant facts, "
                    "statistics, examples, or other reliable evidence."
                ),
                metadata={
                    "evidence_segments": 0,
                },
            )
        )

    # ---------------------------------------------------------
    # Logical fallacies
    # ---------------------------------------------------------

    if fallacies:
        fallacy_names = []

        for segment in fallacies:
            fallacy_type = segment.get("fallacy_type")

            if fallacy_type:
                fallacy_names.append(fallacy_type)

        evidence_items = []

        for segment in fallacies[:5]:
            text = segment.get("text", "")
            fallacy_type = segment.get("fallacy_type")

            if fallacy_type:
                evidence_items.append(
                    f"{fallacy_type}: {text}"
                )
            else:
                evidence_items.append(text)

        feedback.append(
            FeedbackItem(
                category="logic",
                title="Potential logical fallacies detected",
                issue=(
                    f"{len(fallacies)} segment(s) were classified as "
                    "containing a logical fallacy."
                ),
                severity="high",
                evidence=evidence_items,
                explanation=(
                    "The semantic analysis identified reasoning patterns "
                    "that may contain logical fallacies. These can weaken "
                    "an argument if they replace relevant reasoning or evidence."
                ),
                recommendation=(
                    "Review the identified statements and make sure your "
                    "conclusions follow from relevant premises rather than "
                    "from unsupported assumptions or faulty reasoning."
                ),
                metadata={
                    "fallacy_segments": len(fallacies),
                    "fallacy_types": fallacy_names,
                },
            )
        )
    else:
        feedback.append(
            FeedbackItem(
                category="logic",
                title="No logical fallacies detected",
                issue="No segments were classified as logical fallacies.",
                severity="positive",
                evidence=[],
                explanation=(
                    "The semantic analysis did not identify any segments "
                    "explicitly classified as containing a logical fallacy."
                ),
                recommendation=(
                    "Continue checking that your conclusions are supported "
                    "by relevant premises and evidence."
                ),
                metadata={
                    "fallacy_segments": 0,
                },
            )
        )

    # ---------------------------------------------------------
    # Counterarguments and rebuttals
    # ---------------------------------------------------------

    if counterarguments or rebuttals:
        feedback.append(
            FeedbackItem(
                category="logic",
                title="Opposing reasoning is addressed",
                issue=(
                    f"The speech contains {len(counterarguments)} "
                    f"counterargument(s) and {len(rebuttals)} rebuttal(s)."
                ),
                severity="positive",
                evidence=[
                    f"Counterarguments detected: {len(counterarguments)}.",
                    f"Rebuttals detected: {len(rebuttals)}.",
                ],
                explanation=(
                    "Addressing opposing arguments demonstrates that the "
                    "speaker is considering alternative positions and "
                    "attempting to explain why their own position remains stronger."
                ),
                recommendation=(
                    "Focus rebuttals on the actual reasoning behind the "
                    "opposing argument rather than simply rejecting its conclusion."
                ),
                metadata={
                    "counterarguments": len(counterarguments),
                    "rebuttals": len(rebuttals),
                },
            )
        )
    else:
        feedback.append(
            FeedbackItem(
                category="logic",
                title="Opposing reasoning is not addressed",
                issue=(
                    "No counterarguments or rebuttals were detected."
                ),
                severity="medium",
                evidence=[],
                explanation=(
                    "A strong debate argument should consider relevant "
                    "alternative positions and explain why they are less convincing."
                ),
                recommendation=(
                    "Identify the strongest opposing argument and respond "
                    "directly to its reasoning."
                ),
                metadata={
                    "counterarguments": 0,
                    "rebuttals": 0,
                },
            )
        )

    # ---------------------------------------------------------
    # Conclusions
    # ---------------------------------------------------------

    if conclusions:
        feedback.append(
            FeedbackItem(
                category="logic",
                title="Logical conclusions are present",
                issue=(
                    f"{len(conclusions)} conclusion segment(s) were detected."
                ),
                severity="positive",
                evidence=[
                    segment.get("text", "")
                    for segment in conclusions[:5]
                ],
                explanation=(
                    "Explicit conclusions help make the intended result "
                    "of the speaker's reasoning clear."
                ),
                recommendation=(
                    "When reaching a conclusion, briefly connect it back "
                    "to the key premises and evidence presented earlier."
                ),
                metadata={
                    "conclusion_segments": len(conclusions),
                },
            )
        )
    else:
        feedback.append(
            FeedbackItem(
                category="logic",
                title="No clear conclusion detected",
                issue="No conclusion segments were detected.",
                severity="medium",
                evidence=[],
                explanation=(
                    "Without a clear conclusion, the audience may have to "
                    "infer what the preceding reasoning was intended to establish."
                ),
                recommendation=(
                    "End major arguments with a concise conclusion that "
                    "states what your reasoning establishes."
                ),
                metadata={
                    "conclusion_segments": 0,
                },
            )
        )

    # ---------------------------------------------------------
    # Overall logical development
    # ---------------------------------------------------------

    logical_components = sum(
        [
            bool(claims or arguments),
            bool(reasoning),
            bool(evidence),
            bool(conclusions),
        ]
    )

    if logical_components >= 3 and not fallacies:
        feedback.append(
            FeedbackItem(
                category="logic",
                title="Well-developed logical structure",
                issue=(
                    "The speech contains several identifiable components "
                    "of a logical argument."
                ),
                severity="positive",
                evidence=[
                    f"Claims/arguments: {len(claims) + len(arguments)}.",
                    f"Reasoning: {len(reasoning)}.",
                    f"Evidence: {len(evidence)}.",
                    f"Conclusions: {len(conclusions)}.",
                ],
                explanation=(
                    "The speech demonstrates multiple components needed "
                    "for developing a coherent logical argument."
                ),
                recommendation=(
                    "Continue connecting claims, reasoning, evidence, "
                    "and conclusions explicitly."
                ),
                metadata={
                    "logical_components": logical_components,
                    "fallacies": len(fallacies),
                },
            )
        )

    return feedback