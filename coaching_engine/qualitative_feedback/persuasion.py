from typing import List

from ..models.feedback import FeedbackItem
from ..models.session import CoachingSession


def analyze_persuasion(
    session: CoachingSession,
) -> List[FeedbackItem]:
    """
    Analyze persuasive elements in the speaker's speech.

    This module uses the semantic labels produced by the speech-content
    analysis. It does not independently determine whether an argument is
    persuasive; instead, it identifies the presence and balance of
    persuasive building blocks such as:

        - claims
        - arguments
        - evidence
        - examples
        - reasoning
        - rebuttals
        - concessions
        - conclusions

    Returns:
        A list of FeedbackItem objects.
    """

    feedback: List[FeedbackItem] = []

    segments = session.speech_content.get("segments", [])

    if not segments:
        feedback.append(
            FeedbackItem(
                category="persuasion",
                title="No persuasive content available",
                issue="No semantic speech segments were available for analysis.",
                severity="high",
                evidence=[],
                explanation=(
                    "The coaching engine cannot evaluate persuasive elements "
                    "because no semantic speech segments were provided."
                ),
                recommendation=(
                    "Make sure the speech-content analysis successfully "
                    "classified the speech before evaluating persuasion."
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

    # ---------------------------------------------------------
    # Establish argumentative foundation
    # ---------------------------------------------------------

    if claims or arguments:
        feedback.append(
            FeedbackItem(
                category="persuasion",
                title="Clear argumentative position",
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
                    "Persuasion starts with giving the audience a clear "
                    "position or argument to evaluate."
                ),
                recommendation=(
                    "Continue stating your main position clearly before "
                    "developing the supporting reasoning."
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
                category="persuasion",
                title="Weak argumentative foundation",
                issue="No clear claims or arguments were detected.",
                severity="high",
                evidence=[],
                explanation=(
                    "An audience is difficult to persuade when the speaker's "
                    "position is not clearly identifiable."
                ),
                recommendation=(
                    "State your position explicitly and make it clear "
                    "what you want the audience to accept."
                ),
            )
        )

    # ---------------------------------------------------------
    # Evidence and credibility
    # ---------------------------------------------------------

    if evidence:
        feedback.append(
            FeedbackItem(
                category="persuasion",
                title="Evidence strengthens persuasion",
                issue=(
                    f"{len(evidence)} evidence segment(s) were detected."
                ),
                severity="positive",
                evidence=[
                    segment.get("text", "")
                    for segment in evidence[:5]
                ],
                explanation=(
                    "Concrete evidence can increase the credibility of "
                    "an argument and give the audience reasons to accept it."
                ),
                recommendation=(
                    "Continue using specific and relevant evidence to "
                    "support your most important claims."
                ),
                metadata={
                    "evidence_segments": len(evidence),
                },
            )
        )
    else:
        feedback.append(
            FeedbackItem(
                category="persuasion",
                title="Limited evidential support",
                issue="No evidence segments were detected.",
                severity="high",
                evidence=[],
                explanation=(
                    "Arguments based primarily on assertions can be less "
                    "convincing because they provide limited support "
                    "for the audience."
                ),
                recommendation=(
                    "Use concrete facts, statistics, examples, or other "
                    "relevant evidence to strengthen important claims."
                ),
                metadata={
                    "evidence_segments": 0,
                },
            )
        )

    # ---------------------------------------------------------
    # Reasoning
    # ---------------------------------------------------------

    if reasoning:
        feedback.append(
            FeedbackItem(
                category="persuasion",
                title="Reasoning supports your position",
                issue=(
                    f"{len(reasoning)} reasoning segment(s) were detected."
                ),
                severity="positive",
                evidence=[
                    segment.get("text", "")
                    for segment in reasoning[:5]
                ],
                explanation=(
                    "Explaining why a claim follows from its supporting "
                    "points gives the audience a logical path toward "
                    "accepting the conclusion."
                ),
                recommendation=(
                    "Keep explicitly explaining the connection between "
                    "your claims and the evidence supporting them."
                ),
                metadata={
                    "reasoning_segments": len(reasoning),
                },
            )
        )
    else:
        feedback.append(
            FeedbackItem(
                category="persuasion",
                title="Limited explanatory reasoning",
                issue="No reasoning segments were detected.",
                severity="high",
                evidence=[],
                explanation=(
                    "Evidence alone does not necessarily persuade an "
                    "audience unless the speaker explains why that evidence "
                    "supports the claim."
                ),
                recommendation=(
                    "After presenting evidence, explain exactly how it "
                    "supports the point you are trying to prove."
                ),
                metadata={
                    "reasoning_segments": 0,
                },
            )
        )

    # ---------------------------------------------------------
    # Examples
    # ---------------------------------------------------------

    if examples:
        feedback.append(
            FeedbackItem(
                category="persuasion",
                title="Examples improve accessibility",
                issue=(
                    f"{len(examples)} example segment(s) were detected."
                ),
                severity="positive",
                evidence=[
                    segment.get("text", "")
                    for segment in examples[:5]
                ],
                explanation=(
                    "Examples can make abstract or complicated arguments "
                    "easier for an audience to understand and remember."
                ),
                recommendation=(
                    "Use specific examples when they make an argument "
                    "more concrete, while still relying on strong evidence "
                    "for major claims."
                ),
                metadata={
                    "example_segments": len(examples),
                },
            )
        )

    # ---------------------------------------------------------
    # Rebuttal and counterarguments
    # ---------------------------------------------------------

    if rebuttals or counterarguments:
        feedback.append(
            FeedbackItem(
                category="persuasion",
                title="Opposing views are addressed",
                issue=(
                    f"The speech contains {len(rebuttals)} rebuttal segment(s) "
                    f"and {len(counterarguments)} counterargument segment(s)."
                ),
                severity="positive",
                evidence=[
                    f"Rebuttals detected: {len(rebuttals)}.",
                    f"Counterarguments detected: {len(counterarguments)}.",
                ],
                explanation=(
                    "Addressing opposing positions can strengthen persuasion "
                    "because it demonstrates awareness of alternative views "
                    "and gives the speaker an opportunity to defend their own position."
                ),
                recommendation=(
                    "Continue addressing the strongest opposing arguments "
                    "rather than ignoring them."
                ),
                metadata={
                    "rebuttals": len(rebuttals),
                    "counterarguments": len(counterarguments),
                },
            )
        )
    else:
        feedback.append(
            FeedbackItem(
                category="persuasion",
                title="Opposing views are not clearly addressed",
                issue=(
                    "No rebuttal or counterargument segments were detected."
                ),
                severity="medium",
                evidence=[],
                explanation=(
                    "A persuasive debate speech benefits from demonstrating "
                    "why competing positions are weaker or less convincing."
                ),
                recommendation=(
                    "Identify the strongest opposing argument and directly "
                    "explain why your position is better supported."
                ),
                metadata={
                    "rebuttals": 0,
                    "counterarguments": 0,
                },
            )
        )

    # ---------------------------------------------------------
    # Concessions
    # ---------------------------------------------------------

    if concessions:
        feedback.append(
            FeedbackItem(
                category="persuasion",
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
                    "Acknowledging a valid part of an opposing position can "
                    "make a speaker appear more balanced and credible."
                ),
                recommendation=(
                    "Use concessions strategically: acknowledge a valid "
                    "point and then explain why your overall position "
                    "still stands."
                ),
                metadata={
                    "concession_segments": len(concessions),
                },
            )
        )

    # ---------------------------------------------------------
    # Conclusions
    # ---------------------------------------------------------

    if conclusions:
        feedback.append(
            FeedbackItem(
                category="persuasion",
                title="A clear conclusion is present",
                issue=(
                    f"{len(conclusions)} conclusion segment(s) were detected."
                ),
                severity="positive",
                evidence=[
                    segment.get("text", "")
                    for segment in conclusions[:5]
                ],
                explanation=(
                    "A clear conclusion gives the audience a final "
                    "statement of the position you want them to accept."
                ),
                recommendation=(
                    "End major arguments by clearly connecting the "
                    "supporting points back to your main claim."
                ),
                metadata={
                    "conclusion_segments": len(conclusions),
                },
            )
        )

    # ---------------------------------------------------------
    # Overall support balance
    # ---------------------------------------------------------

    support_count = len(evidence) + len(reasoning) + len(examples)

    if (claims or arguments) and support_count == 0:
        feedback.append(
            FeedbackItem(
                category="persuasion",
                title="Arguments need stronger support",
                issue=(
                    "The speech contains argumentative positions but no "
                    "detected evidence, reasoning, or examples."
                ),
                severity="high",
                evidence=[],
                explanation=(
                    "Persuasion is stronger when the audience is given "
                    "multiple reasons to accept a claim rather than "
                    "being asked to accept it as an assertion."
                ),
                recommendation=(
                    "For each major claim, provide a clear reason and "
                    "at least one relevant form of supporting evidence "
                    "or example."
                ),
                metadata={
                    "claims": len(claims),
                    "arguments": len(arguments),
                    "evidence": len(evidence),
                    "reasoning": len(reasoning),
                    "examples": len(examples),
                },
            )
        )

    return feedback