import json
from typing import Any, Dict


SYSTEM_PROMPT = """
You are an expert debate coach.

Your task is to analyze a speaker's debate performance and provide
specific, evidence-based coaching feedback.

You must:
- Base your analysis only on the information provided.
- Do not invent statements that are not present in the speech.
- Distinguish between observations and interpretations.
- Identify specific weaknesses and explain how they affect the argument.
- Give practical recommendations that the speaker can apply.
- Be concise but useful.
- Do not evaluate speaking speed, pauses, fillers, or stutters.
  Those are handled separately by the quantitative analysis.
- Focus on qualitative aspects of debate performance.

Return your response as valid JSON only.

The JSON must contain a top-level object with a key called "feedback".
"feedback" must be a list of feedback objects.

Each feedback object must contain:

{
    "category": "argumentation | rebuttal | structure | persuasion | logic",
    "title": "short descriptive title",
    "issue": "specific problem or observation",
    "severity": "high | medium | low | positive",
    "evidence": ["exact or short excerpts from the speech"],
    "explanation": "why this matters",
    "recommendation": "specific advice for improvement",
    "metadata": {}
}

Do not include markdown.
Do not wrap the JSON in ```json fences.
"""


def build_qualitative_prompt(
    category: str,
    speech_content: Dict[str, Any],
) -> str:
    """
    Build a prompt for qualitative analysis of a debate speech.

    Args:
        category:
            The qualitative category being analyzed.

        speech_content:
            Semantic speech analysis containing classified segments.

    Returns:
        A prompt string for the LLM.
    """

    if not category.strip():
        raise ValueError("category cannot be empty.")

    if not isinstance(speech_content, dict):
        raise TypeError("speech_content must be a dictionary.")

    category_instructions = {
        "argumentation": """
Evaluate the speaker's argumentation.

Focus on:
- clarity of claims
- development of arguments
- quality of reasoning
- use of supporting evidence
- whether important claims appear unsupported
- development of ideas
- strength of argumentative support

Do not claim that a specific claim is unsupported merely because
the data does not explicitly connect claims to evidence.
""",

        "rebuttal": """
Evaluate the speaker's rebuttal technique.

Focus on:
- identification of opposing arguments
- directness of responses
- quality of rebuttals
- use of reasoning against opposing positions
- use of evidence in rebuttals
- concessions
- whether the speaker actually engages with opposing reasoning

Do not invent an opposing argument that is not present in the data.
""",

        "structure": """
Evaluate the organization and structure of the speech.

Focus on:
- clarity of the main position
- progression of arguments
- transitions between ideas
- relationship between claims, reasoning, and evidence
- placement of rebuttals
- conclusions
- overall coherence

Do not infer exact relationships that are not represented in the input.
""",

        "persuasion": """
Evaluate the persuasive effectiveness of the speech.

Focus on:
- clarity of the speaker's position
- strength of supporting reasoning
- use of evidence
- use of examples
- engagement with opposing views
- concessions
- conclusions
- credibility and convincingness of the presented reasoning

Do not evaluate vocal delivery metrics such as speaking speed or pauses.
""",

        "logic": """
Evaluate the logical quality of the speech.

Focus on:
- reasoning
- connections between claims and supporting points
- unsupported assertions
- logical consistency
- use of evidence
- treatment of opposing reasoning
- detected logical fallacies
- conclusions

Do not independently invent logical fallacies. Use detected fallacy
information when available and explain its possible impact.
""",
    }

    instructions = category_instructions.get(category)

    if instructions is None:
        raise ValueError(
            f"Unsupported qualitative category: {category}"
        )

    speech_json = json.dumps(
        speech_content,
        indent=2,
        ensure_ascii=False,
    )

    return f"""
Analyze the following debate speech for the category:

CATEGORY:
{category}

CATEGORY-SPECIFIC INSTRUCTIONS:
{instructions}

SEMANTIC SPEECH DATA:
{speech_json}

Return only valid JSON using the required response structure.
"""