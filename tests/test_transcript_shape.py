"""
audio/transcript_shape.to_canonical: one normaliser for every
transcription shape, and the helpers new code relies on.
"""

from audio.transcript_shape import to_canonical


def test_nested_words_become_flat_globally_indexed(transcription):
    canon = to_canonical(transcription)

    assert [s.id for s in canon.segments] == ["s_000", "s_001", "s_002"]
    assert len(canon.words) == 18
    assert [w.i for w in canon.words] == list(range(18))

    # word_range is [lo, hi) and contiguous across segments
    assert [s.word_range for s in canon.segments] == [(0, 6), (6, 12), (12, 18)]

    # words carry their segment id; text is stripped
    assert canon.words[0].text == "Um"
    assert canon.words[0].segment_id == "s_000"
    assert canon.words[6].text == "Like,"
    assert canon.words[6].segment_id == "s_001"

    # segment times come from the transcript
    assert (canon.segments[1].start, canon.segments[1].end) == (3.10, 5.20)


def test_flat_top_level_words_are_placed_into_segments(transcription):
    """A provider that returns words unnested still normalises."""
    flat = {
        "segments": [
            {k: v for k, v in seg.items() if k != "words"}
            for seg in transcription["segments"]
        ],
        "words": [w for seg in transcription["segments"] for w in seg["words"]],
    }
    nested = to_canonical(transcription)
    canon = to_canonical(flat)

    assert canon.to_dict() == nested.to_dict()


def test_segment_without_words_or_times_is_dropped_and_others_survive():
    canon = to_canonical(
        {
            "segments": [
                {"start": 0.0, "end": 1.0, "text": "a", "words": [
                    {"word": " a", "start": 0.0, "end": 1.0}
                ]},
                {"text": "no timing, no words"},
                {"text": "words only", "words": [
                    {"word": " b", "start": 2.0, "end": 2.5},
                    {"word": " c", "start": 2.6, "end": 3.0},
                ]},
            ]
        }
    )

    # ids stay tied to transcript position, so s_001 is skipped
    assert [s.id for s in canon.segments] == ["s_000", "s_002"]
    assert canon.segments[1].start == 2.0
    assert canon.segments[1].end == 3.0
    assert canon.segments[1].word_range == (1, 3)


def test_words_without_timing_or_text_are_dropped():
    canon = to_canonical(
        {
            "segments": [
                {"start": 0.0, "end": 3.0, "text": "x y z", "words": [
                    {"word": " x", "start": 0.0, "end": 1.0},
                    {"word": " y", "start": None, "end": 2.0},
                    {"word": "  ", "start": 2.0, "end": 2.5},
                    {"word": " z", "start": 2.5, "end": 3.0},
                ]}
            ]
        }
    )
    assert [w.text for w in canon.words] == ["x", "z"]
    assert canon.segments[0].word_range == (0, 2)


def test_span_and_excerpt_helpers(transcription):
    canon = to_canonical(transcription)

    assert canon.span(["s_001", "s_002"]) == (3.10, 7.70)
    assert canon.span(["s_002", "s_001"]) == (3.10, 7.70)
    assert canon.span(["nope"]) is None
    assert canon.span(["nope", "s_000"]) == (0.50, 2.60)

    assert canon.word_range_for(["s_001", "s_002"]) == (6, 18)
    assert canon.excerpt((6, 18), max_words=4) == "Like, this this evidence"
    assert canon.excerpt((12, 18)) == "You know, they never answered it."


def test_empty_transcription():
    canon = to_canonical({})
    assert canon.words == ()
    assert canon.segments == ()
    assert canon.to_dict() == {"words": [], "segments": []}
