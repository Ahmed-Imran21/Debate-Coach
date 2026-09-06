import re


# Maximum time between repeated words for them to be considered
# part of the same disfluency.
MAX_REPETITION_GAP = 0.8

# Short words are more likely to be repeated naturally
# ("the the", "I I", etc.), so we keep them but mark them
# as word repetitions rather than claiming they are definitely
# phonetic stutters.
MIN_FRAGMENT_LENGTH = 1


def normalize_word(word):
    """
    Normalize a word for comparison.
    """
    word = word.lower().strip()

    cleaned = ""

    for char in word:
        if char.isalnum() or char == "'":
            cleaned += char

    return cleaned


def get_transcript_words(transcription):
    """
    Extract word-level timestamp information from transcription.
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


def detect_repeated_words(words):
    """
    Detect consecutive repeated words.

    Examples:
        "I I think"
        "the the problem"
        "we we we need"

    These are classified as word repetitions rather than
    guaranteed phonetic stutters.
    """
    instances = []

    i = 0

    while i < len(words) - 1:

        current = words[i]
        next_word = words[i + 1]

        if (
            current["normalized"]
            and current["normalized"] == next_word["normalized"]
        ):

            # Check timestamp gap if timestamps are available.
            gap = None

            if (
                current["end"] is not None
                and next_word["start"] is not None
            ):
                gap = next_word["start"] - current["end"]

            if gap is None or gap <= MAX_REPETITION_GAP:

                repeated_words = [current, next_word]

                j = i + 2

                # Detect:
                # "I I I think"
                while j < len(words):

                    previous = words[j - 1]
                    candidate = words[j]

                    if (
                        candidate["normalized"]
                        != current["normalized"]
                    ):
                        break

                    if (
                        previous["end"] is not None
                        and candidate["start"] is not None
                        and candidate["start"] - previous["end"]
                        > MAX_REPETITION_GAP
                    ):
                        break

                    repeated_words.append(candidate)
                    j += 1

                instances.append({
                    "type": "word_repetition",
                    "text": " ".join(
                        word["word"]
                        for word in repeated_words
                    ),
                    "start": repeated_words[0]["start"],
                    "end": repeated_words[-1]["end"]
                })

                i = j
                continue

        i += 1

    return instances


def detect_repeated_fragments(words):
    """
    Detect very short repeated fragments that may appear in
    transcripts such as:

        "I-I"
        "b-b-but"
        "w-w-we"

    This relies on the transcript actually preserving the
    repeated fragment. Whisper may not always preserve these.
    """

    instances = []

    for word in words:
        original = word["word"].strip()

        # Remove surrounding punctuation while preserving
        # internal hyphens.
        cleaned = original.strip(".,!?;:\"'()[]{}")

        if "-" not in cleaned:
            continue

        parts = [
            part.strip()
            for part in cleaned.split("-")
            if part.strip()
        ]

        if len(parts) < 2:
            continue

        normalized_parts = [
            normalize_word(part)
            for part in parts
        ]

        # Check whether the first fragments are repeated.
        first_fragment = normalized_parts[0]

        if not first_fragment:
            continue

        repetition_count = 1

        for part in normalized_parts[1:]:
            if part == first_fragment:
                repetition_count += 1
            else:
                break

        if repetition_count >= 2:

            instances.append({
                "type": "fragment_repetition",
                "text": original,
                "start": word["start"],
                "end": word["end"]
            })

    return instances


def remove_overlapping_instances(instances):
    """
    Remove duplicate detections that refer to the same
    transcript location.
    """

    if not instances:
        return []

    instances = sorted(
        instances,
        key=lambda instance: (
            instance.get("start")
            if instance.get("start") is not None
            else float("inf")
        )
    )

    filtered = []

    for instance in instances:

        if not filtered:
            filtered.append(instance)
            continue

        previous = filtered[-1]

        previous_start = previous.get("start")
        previous_end = previous.get("end")
        current_start = instance.get("start")
        current_end = instance.get("end")

        if (
            previous_start is not None
            and previous_end is not None
            and current_start is not None
            and current_end is not None
        ):
            overlaps = (
                current_start <= previous_end
                and current_end >= previous_start
            )

            if overlaps:
                continue

        filtered.append(instance)

    return filtered


def detect_stutters(transcription):
    """
    Detect likely stuttering/disfluency patterns.

    Returns:
        {
            "count": int,
            "instances": [...]
        }

    Important:
        These are detected repetition patterns, not a clinical
        diagnosis of stuttering.
    """

    words = get_transcript_words(transcription)

    repeated_words = detect_repeated_words(words)
    repeated_fragments = detect_repeated_fragments(words)

    instances = repeated_words + repeated_fragments

    instances = remove_overlapping_instances(instances)

    return {
        "count": len(instances),
        "instances": instances
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

    results = detect_stutters(transcription)

    print(json.dumps(
        results,
        indent=4,
        ensure_ascii=False
    ))