import json
from typing import Any, Dict


SYSTEM_PROMPT = """
You are an expert debate coach analyzing a speaker's debate performance.

Your task is to provide specific, evidence-based coaching feedback.

Rules:

- Base your analysis only on the information provided.
- Never invent statements, arguments, evidence, or opposing positions.
- Distinguish observations from interpretations.
- Identify specific strengths or weaknesses.
- Explain why an issue matters to debate performance.
- Give practical recommendations that the speaker can apply.
- Keep feedback concise but useful.
- Focus only on qualitative debate performance.
- Do NOT evaluate speaking speed, pauses, fillers, or stutters.
- Those aspects are handled separately by the quantitative analysis.
- Use the provided semantic labels as evidence.
- Do not assume relationships between claims and evidence that are
  not represented in the input.
- Do not independently invent logical fallacies.
- If a detected fallacy is present, explain its possible impact rather
  than claiming more than the data supports.

You must return only the structured response requested by the schema.
"""


FEEDBACK_RESPONSE_SCHEMA = {
    "type": "object",
    "properties": {
        "feedback": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "category": {
                        "type": "string",
                        "enum": [
                            "argumentation",
                            "rebuttal",
                            "structure",
                            "persuasion",
                            "logic",
                        ],
                    },
                    "title": {
                        "type": "string"
                    },
                    "issue": {
                        "type": "string"
                    },
                    "severity": {
                        "type": "string",
                        "enum": [
                            "high",
                            "medium",
                            "low",
                            "positive",
                        ],
                    },
                    "evidence": {
                        "type": "array",
                        "items": {
                            "type": "string"
                        },
                    },
                    "explanation": {
                        "type": "string"
                    },
                    "recommendation": {
                        "type": "string"
                    },
                    "metadata": {
                        "type": "object",
                        "properties": {},
                        "additionalProperties": False,
                    },
                },
                "required": [
                    "category",
                    "title",
                    "issue",
                    "severity",
                    "evidence",
                    "explanation",
                    "recommendation",
                    "metadata",
                ],
                "additionalProperties": False,
            },
        }
    },
    "required": [
        "feedback"
    ],
    "additionalProperties": False,
}


CATEGORY_INSTRUCTIONS = {
    "argumentation": """
Evaluate the speaker's argumentation.

Focus on:

- clarity of claims
- development of arguments
- quality of reasoning
- use of supporting evidence
- use of examples
- whether important claims appear unsupported
- development of ideas
- strength of argumentative support
- clarity of conclusions

Do not claim that a specific claim is unsupported merely because
the data does not explicitly connect claims to evidence.

Look for both strengths and weaknesses where appropriate.
""",

    "rebuttal": """
Evaluate the speaker's rebuttal technique.

Focus on:

- identification of opposing arguments
- directness of responses
- quality of rebuttals
- reasoning used against opposing positions
- evidence used in rebuttals
- concessions
- whether the speaker actually engages with opposing reasoning
- whether rebuttals appear relevant to the opposing position

Do not invent an opposing argument that is not present in the data.
""",

    "structure": """
Evaluate the organization and structure of the speech.

Focus on:

- clarity of the main position
- progression of arguments
- organization of ideas
- transitions between ideas
- relationship between claims, reasoning, and evidence
- placement of rebuttals
- conclusions
- overall coherence
- whether the speech develops in a logical sequence

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
- credibility of the presented reasoning
- how convincing the argument appears based on the available evidence

Do not evaluate vocal delivery metrics such as speaking speed,
pauses, fillers, or stutters.
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

Do not independently invent logical fallacies.

If a segment is explicitly labeled as a logical fallacy, use that
information and explain its possible impact on the argument.

Do not claim that an argument is logically invalid unless the
provided information supports that conclusion.
""",
}


def build_qualitative_prompt(
    category: str,
    speech_content: Dict[str, Any],
) -> str:
    """
    Build a category-specific prompt for qualitative debate analysis.
    """

    if not isinstance(category, str):
        raise TypeError("category must be a string.")

    if not category.strip():
        raise ValueError("category cannot be empty.")

    if not isinstance(speech_content, dict):
        raise TypeError("speech_content must be a dictionary.")

    category = category.strip().lower()

    instructions = CATEGORY_INSTRUCTIONS.get(category)

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

Provide useful coaching feedback based only on the supplied data.

Include positive feedback when the speaker demonstrates a clear
strength.

For weaknesses:

1. Identify the specific issue.
2. Use evidence from the supplied speech data.
3. Explain why the issue matters.
4. Give a practical recommendation.

Do not invent information that is not present in the semantic
speech data.
"""