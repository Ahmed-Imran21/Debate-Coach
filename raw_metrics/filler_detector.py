from collections import Counter


# Common English filler words/phrases.
# Keep this list conservative to avoid incorrectly classifying
# normal words as fillers.
FILLER_WORDS = {
    "um",
    "uh",
    "erm",
    "hmm",
    "like",
    "basically",
    "actually",
    "literally",
    "well",
}

# Multi-word fillers need to be checked separately.
FILLER_PHRASES = {
    "you know",
    "i mean",
    "kind of",
    "sort of",
}


def normalize_word(word):
    """
    Normalize a transcript word for comparison.

    Keeps apostrophes but removes most punctuation.
    """
    word = word.lower().strip()

    cleaned = ""

    for char in word:
        if char.isalnum() or char == "'":
            cleaned += char

    return cleaned


def get_transcript_words(transcription):
    """
    Extract word-level information from transcription.json.

    Returns a flat list of word dictionaries.
    """
    words = []

    for segment in transcription.get("segments", []):
        for word in segment.get("words", []):
            text = word.get("word", "").strip()

            if not text:
                continue

            words.append({
                "word": text,
                "normalized": normalize_word(text),
                "start": word.get("start"),
                "end": word.get("end"),
                "probability": word.get("probability")
            })

    return words


def detect_single_word_fillers(words):
    """
    Detect single-word fillers.
    """
    instances = []
    counts = Counter()

    for word in words:
        normalized = word["normalized"]

        if normalized in FILLER_WORDS:
            filler = normalized

            counts[filler] += 1

            instances.append({
                "word": word["word"],
                "start": word["start"],
                "end": word["end"],
                "probability": word["probability"]
            })

    return counts, instances


def detect_phrase_fillers(words):
    """
    Detect multi-word filler phrases such as:
        "you know"
        "i mean"
        "kind of"

    Uses consecutive transcript words.
    """
    instances = []
    counts = Counter()

    normalized_words = [
        word["normalized"]
        for word in words
    ]

    for phrase in FILLER_PHRASES:
        phrase_words = phrase.split()
        phrase_length = len(phrase_words)

        for i in range(len(words) - phrase_length + 1):
            current_words = normalized_words[
                i:i + phrase_length
            ]

            if current_words == phrase_words:
                start_word = words[i]
                end_word = words[i + phrase_length - 1]

                counts[phrase] += 1

                instances.append({
                    "phrase": phrase,
                    "start": start_word["start"],
                    "end": end_word["end"],
                    "text": " ".join(
                        word["word"]
                        for word in words[i:i + phrase_length]
                    )
                })

    return counts, instances


def detect_fillers(transcription):
    """
    Detect filler words and phrases in a transcription.

    Returns:
        {
            "count": int,
            "words": {
                "um": 3,
                "uh": 2,
                ...
            },
            "instances": [...]
        }
    """

    words = get_transcript_words(transcription)

    word_counts, word_instances = detect_single_word_fillers(words)
    phrase_counts, phrase_instances = detect_phrase_fillers(words)

    total_counts = word_counts + phrase_counts
    all_instances = word_instances + phrase_instances

    # Sort instances chronologically.
    all_instances.sort(
        key=lambda instance: (
            instance.get("start")
            if instance.get("start") is not None
            else float("inf")
        )
    )

    return {
        "count": sum(total_counts.values()),
        "words": dict(total_counts),
        "instances": all_instances
    }


if __name__ == "__main__":
    import json
    from pathlib import Path

    session_id = "session_20260823_233450"
    transcription_path = (
        Path("sessions")
        / session_id
        / "transcription.json"
    )

    with open(transcription_path, "r", encoding="utf-8") as file:
        transcription = json.load(file)

    results = detect_fillers(transcription)

    print(json.dumps(
        results,
        indent=4,
        ensure_ascii=False
    ))