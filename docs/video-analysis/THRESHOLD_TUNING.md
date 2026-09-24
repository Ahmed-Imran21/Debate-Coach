# Threshold tuning

Every threshold in `visual_analysis/config.py` is provisional — copied from the task
document's own defaults, not derived from labelled data. This is how to check them
against reality once real recordings exist.

## 1. Collect stored tracks

Any session recorded with `VIDEO_ANALYSIS_ENABLED` on has its raw `VisualSignalTrack`
stored at `visual_signals.json.gz` under that session's object-key prefix
(`app/services/visual_signals.py`'s `track_key()`). Download a representative set —
varied lighting, framing, device tiers, and speaking styles — and save each as
`<session_id>.json.gz` (or decompress to `<session_id>.json`; the evaluation script
accepts either) in one directory.

## 2. Label ground truth by hand

For each track, watch the corresponding recording (or the debug-page-style readouts, if
you have them) and write down every interval where the speaker was genuinely looking
away, had their head down, or was gesturing — using your own judgment, not the
thresholds you're trying to check. Put every session's labels in one CSV:

```csv
session_id,type,start,end
s-01,gaze_away,12.4,15.9
s-01,head_down,40.0,41.2
s-01,gesture,50.1,51.8
s-01,gesture,52.0,53.4
s-02,gaze_away,3.0,7.5
```

- `type` is one of `gaze_away`, `head_down`, `gesture` — the three event types the task
  document asks to be labelled and evaluated. (`hands_still`, `face_lost`,
  `second_person`, and `analysis_degraded` aren't included: the first three are large,
  usually-unambiguous stretches that are easy to sanity-check by eye without formal
  labelling, and `analysis_degraded` is an instantaneous marker of a measured condition,
  not a behavior to detect.)
- `start`/`end` in seconds, matching the track's own clock (seconds since audio start).
- One row per interval. A speaker who looks away three separate times gets three rows.

## 3. Run the evaluator

```bash
.venv/bin/python scripts/evaluate_visual_events.py \
  --tracks-dir path/to/tracks \
  --labels path/to/labels.csv
```

For each of the three labelled event types, this prints precision, recall, and mean IoU
of matched pairs at IoU >= 0.3 (a predicted and a labelled interval "match" if they
overlap by at least 30% of their union — loose enough to tolerate a couple hundred
milliseconds of boundary disagreement, strict enough that a prediction covering the whole
session doesn't trivially match everything).

Matching is greedy and one-to-one: each ground-truth interval is paired with the
highest-IoU unmatched prediction of the same type (if any clears the threshold); anything
left over on either side counts against recall or precision respectively.

The script only reads local files (the two paths given on the command line) — nothing it
does touches the network, the database, or object storage.

## 4. Adjust and re-run

If recall is low for an event type, its `_MIN_S` / cone thresholds in
`visual_analysis/config.py` are probably too strict (real instances are shorter or
smaller than the constant currently requires). If precision is low, they're probably too
loose (noise is crossing the threshold). Change one constant at a time, re-run, and keep
a note of what changed and why — the config module's own comment says everything in it is
provisional; this is the process that's supposed to eventually make it not be.

Reasonable targets before calling a threshold "tuned": precision and recall both above
0.7, mean IoU above 0.5, on at least 15-20 labelled minutes spread across multiple
sessions. Fewer than that and you're tuning to noise in your own labelling.
