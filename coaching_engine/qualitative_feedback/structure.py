from typing import List

from ..models.feedback import FeedbackItem
from ..models.session import CoachingSession


def analyze_structure(
    session: CoachingSession,
) -> List[FeedbackItem]:
    """
    Analyze the structural organization of a debate speech.

    This module uses the semantic labels produced by the speech-content
    analysis to evaluate the presence of structural components such as:

        - claims
        - arguments
        - reasoning
        - evidence
        - examples
        - rebuttals
        - conclusions

    The current speech-content representation does not explicitly encode
    higher-level relationships or argument trees. Therefore, this module
    evaluates structural patterns based on the semantic segments available.

    Returns:
        A list of FeedbackItem objects.
    """

    feedback: List[FeedbackItem] = []

    segments = session.speech_content.get("segments", [])

    if not segments:
        feedback.append(
            FeedbackItem(
                category="structure",
                title="No structural content available",
                issue="No semantic speech segments were available for analysis.",
                severity="high",
                evidence=[],
                explanation=(
                    "The coaching engine cannot evaluate speech structure "
                    "because no semantic segments were provided."
                ),
                recommendation=(
                    "Make sure the speech-content analysis successfully "
                    "classified the speech before evaluating structure."
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

    examples = [
        segment
        for segment in segments
        if "example" in segment.get("labels", [])
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

    concessions = [
        segment
        for segment in segments
        if "concession" in segment.get("labels", [])
    ]

    conclusions = [
        segment
        for segment in segments
        if "conclusion" in segment.get("labels", [])
    ]

    # ---------------------------------------------------------
    # Opening / main position
    # ---------------------------------------------------------

    if claims:
        feedback.append(
            FeedbackItem(
                category="structure",
                title="Main positions are identifiable",
                issue=(
                    f"{len(claims)} claim segment(s) were detected."
                ),
                severity="positive",
                evidence=[
                    segment.get("text", "")
                    for segment in claims[:5]
                ],
                explanation=(
                    "Clear claims give the audience identifiable positions "
                    "to follow throughout the speech."
                ),
                recommendation=(
                    "State your main claim early and make each major "
                    "argument clearly connected to your overall position."
                ),
                metadata={
                    "claims": len(claims),
                },
            )
        )
    else:
        feedback.append(
            FeedbackItem(
                category="structure",
                title="Main position is not clearly identified",
                issue="No claim segments were detected.",
                severity="high",
                evidence=[],
                explanation=(
                    "Without a clearly identifiable claim, it can be "
                    "difficult for the audience to understand the central "
                    "position of the speech."
                ),
                recommendation=(
                    "Begin by clearly stating the position you are defending."
                ),
                metadata={
                    "claims": 0,
                },
            )
        )

    # ---------------------------------------------------------
    # Argument development
    # ---------------------------------------------------------

    if arguments:
        feedback.append(
            FeedbackItem(
                category="structure",
                title="Arguments are developed",
                issue=(
                    f"{len(arguments)} argument segment(s) were detected."
                ),
                severity="positive",
                evidence=[
                    segment.get("text", "")
                    for segment in arguments[:5]
                ],
                explanation=(
                    "The speech contains identifiable argumentative sections "
                    "rather than only isolated claims."
                ),
                recommendation=(
                    "Continue separating major arguments clearly and "
                    "develop each one before moving to the next."
                ),
                metadata={
                    "arguments": len(arguments),
                },
            )
        )
    else:
        feedback.append(
            FeedbackItem(
                category="structure",
                title="Arguments are not clearly developed",
                issue="No argument segments were detected.",
                severity="high",
                evidence=[],
                explanation=(
                    "A structured debate speech should develop its claims "
                    "through distinct arguments."
                ),
                recommendation=(
                    "Break your position into clear arguments and explain "
                    "each argument separately."
                ),
                metadata={
                    "arguments": 0,
                },
            )
        )

    # ---------------------------------------------------------
    # Reasoning and evidence
    # ---------------------------------------------------------

    if reasoning:
        feedback.append(
            FeedbackItem(
                category="structure",
                title="Reasoning is incorporated",
                issue=(
                    f"{len(reasoning)} reasoning segment(s) were detected."
                ),
                severity="positive",
                evidence=[
                    segment.get("text", "")
                    for segment in reasoning[:5]
                ],
                explanation=(
                    "Reasoning helps develop an argument instead of leaving "
                    "the audience to infer how the points are connected."
                ),
                recommendation=(
                    "Continue explaining the reasoning behind each major "
                    "argument before moving to the next point."
                ),
                metadata={
                    "reasoning": len(reasoning),
                },
            )
        )
    else:
        feedback.append(
            FeedbackItem(
                category="structure",
                title="Arguments lack explicit reasoning",
                issue="No reasoning segments were detected.",
                severity="high",
                evidence=[],
                explanation=(
                    "Without explicit reasoning, the structure of an "
                    "argument can appear incomplete."
                ),
                recommendation=(
                    "After introducing an argument, explain why the "
                    "supporting points lead to your conclusion."
                ),
                metadata={
                    "reasoning": 0,
                },
            )
        )

    if evidence:
        feedback.append(
            FeedbackItem(
                category="structure",
                title="Supporting evidence is included",
                issue=(
                    f"{len(evidence)} evidence segment(s) were detected."
                ),
                severity="positive",
                evidence=[
                    segment.get("text", "")
                    for segment in evidence[:5]
                ],
                explanation=(
                    "Evidence provides supporting material that can be "
                    "placed within the development of an argument."
                ),
                recommendation=(
                    "Introduce evidence at the point where it directly "
                    "supports the argument being discussed."
                ),
                metadata={
                    "evidence": len(evidence),
                },
            )
        )
    else:
        feedback.append(
            FeedbackItem(
                category="structure",
                title="Arguments lack detected evidence",
                issue="No evidence segments were detected.",
                severity="medium",
                evidence=[],
                explanation=(
                    "Arguments can feel structurally incomplete when "
                    "important claims have no supporting evidence."
                ),
                recommendation=(
                    "Include relevant evidence when developing major arguments."
                ),
                metadata={
                    "evidence": 0,
                },
            )
        )

    # ---------------------------------------------------------
    # Examples
    # ---------------------------------------------------------

    if examples:
        feedback.append(
            FeedbackItem(
                category="structure",
                title="Examples are incorporated",
                issue=(
                    f"{len(examples)} example segment(s) were detected."
                ),
                severity="positive",
                evidence=[
                    segment.get("text", "")
                    for segment in examples[:5]
                ],
                explanation=(
                    "Examples can help develop an argument by making "
                    "abstract points more concrete."
                ),
                recommendation=(
                    "Use examples where they clarify an argument, "
                    "but keep them directly relevant to the point."
                ),
                metadata={
                    "examples": len(examples),
                },
            )
        )

    # ---------------------------------------------------------
    # Rebuttal placement
    # ---------------------------------------------------------

    if rebuttals:
        feedback.append(
            FeedbackItem(
                category="structure",
                title="Rebuttal content is present",
                issue=(
                    f"{len(rebuttals)} rebuttal segment(s) were detected."
                ),
                severity="positive",
                evidence=[
                    segment.get("text", "")
                    for segment in rebuttals[:5]
                ],
                explanation=(
                    "Including rebuttals adds another structural component "
                    "by allowing the speech to engage with opposing positions."
                ),
                recommendation=(
                    "Clearly signal when you are moving from your own "
                    "argument to addressing the opposing position."
                ),
                metadata={
                    "rebuttals": len(rebuttals),
                },
            )
        )

    if counterarguments:
        feedback.append(
            FeedbackItem(
                category="structure",
                title="Opposing positions are incorporated",
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
                    "Explicitly introducing opposing positions can make "
                    "the structure of a debate speech easier to follow."
                ),
                recommendation=(
                    "Clearly distinguish the opposing position from "
                    "your response to it."
                ),
                metadata={
                    "counterarguments": len(counterarguments),
                },
            )
        )

    # ---------------------------------------------------------
    # Concessions
    # ---------------------------------------------------------

    if concessions:
        feedback.append(
            FeedbackItem(
                category="structure",
                title="Concessions are incorporated",
                issue=(
                    f"{len(concessions)} concession segment(s) were detected."
                ),
                severity="positive",
                evidence=[
                    segment.get("text", "")
                    for segment in concessions[:5]
                ],
                explanation=(
                    "Concessions can create a structured transition between "
                    "acknowledging an opposing point and defending your own position."
                ),
                recommendation=(
                    "Use concessions strategically and follow them with "
                    "a clear explanation of why your position still stands."
                ),
                metadata={
                    "concessions": len(concessions),
                },
            )
        )

    # ---------------------------------------------------------
    # Conclusion
    # ---------------------------------------------------------

    if conclusions:
        feedback.append(
            FeedbackItem(
                category="structure",
                title="A conclusion is present",
                issue=(
                    f"{len(conclusions)} conclusion segment(s) were detected."
                ),
                severity="positive",
                evidence=[
                    segment.get("text", "")
                    for segment in conclusions[:5]
                ],
                explanation=(
                    "A conclusion gives the speech a clear endpoint and "
                    "allows the speaker to restate what the preceding "
                    "arguments establish."
                ),
                recommendation=(
                    "Use the conclusion to briefly reinforce your main "
                    "claim and the strongest supporting arguments."
                ),
                metadata={
                    "conclusions": len(conclusions),
                },
            )
        )
    else:
        feedback.append(
            FeedbackItem(
                category="structure",
                title="No clear conclusion detected",
                issue="No conclusion segments were detected.",
                severity="medium",
                evidence=[],
                explanation=(
                    "Without a clear conclusion, the audience may not know "
                    "when the main argument has been completed or what "
                    "the speaker ultimately wants them to accept."
                ),
                recommendation=(
                    "End the speech with a concise conclusion that "
                    "reinforces your main position."
                ),
                metadata={
                    "conclusions": 0,
                },
            )
        )

    # ---------------------------------------------------------
    # Overall structural development
    # ---------------------------------------------------------

    structural_components = sum(
        [
            bool(claims),
            bool(arguments),
            bool(reasoning),
            bool(evidence),
            bool(rebuttals or counterarguments),
            bool(conclusions),
        ]
    )

    if structural_components >= 4:
        feedback.append(
            FeedbackItem(
                category="structure",
                title="Multiple structural components are present",
                issue=(
                    "The speech contains several identifiable components "
                    "of a structured debate argument."
                ),
                severity="positive",
                evidence=[
                    f"Claims: {len(claims)}.",
                    f"Arguments: {len(arguments)}.",
                    f"Reasoning: {len(reasoning)}.",
                    f"Evidence: {len(evidence)}.",
                    f"Rebuttals: {len(rebuttals)}.",
                    f"Conclusions: {len(conclusions)}.",
                ],
                explanation=(
                    "The speech demonstrates several components that "
                    "contribute to a complete debate structure."
                ),
                recommendation=(
                    "Focus on making the transitions between these "
                    "components clear so the audience can easily follow "
                    "the progression of your argument."
                ),
                metadata={
                    "structural_components": structural_components,
                },
            )
        )

    return feedback