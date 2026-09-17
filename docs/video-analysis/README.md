# Video analysis

An optional, feature-flagged addition to Debate Coach: on-device camera analysis of head
direction, camera-facing, and hand movement, correlated with the argument structure a
session already produces, with a separate LLM pass turning the correlated moments into
coaching prose. With both feature flags off, the app is byte-identical to before this
existed. No video, frame, image, or landmark ever leaves the browser — only small numeric
signals derived from each analyzed frame.

This document is the map. The Pydantic models in `visual_analysis/schema.py` and the
TypeScript types in `web/features/video-analysis/types.ts` / `web/lib/types.ts` are the
actual source of truth for every shape mentioned here; if this document and the code
disagree, trust the code and fix this document.

## Feature flags

- Backend: `VIDEO_ANALYSIS_ENABLED` (`app/core/config.py`), default `false`.
- Frontend: `NEXT_PUBLIC_VIDEO_ANALYSIS_ENABLED`, default unset/false.

Both must be on for any part of this feature to activate. With either off: the signal
upload route 404s, session creation ignores `video_analysis`, the report omits/nulls the
new fields, and the browser downloads nothing extra (MediaPipe is loaded only after a
user opts in, behind the frontend flag).

## Data flow

```
Browser (opted in)
  Setup screen: framing checks, benchmark, gaze calibration, right-hand calibration, context
  Recording: MediaPipe Face Landmarker + Hand Landmarker on camera frames, ~10fps adaptive
  Each analyzed frame -> ~17 derived numbers -> frame discarded immediately
  VisualSignalTrack (gzipped JSON) held in IndexedDB until the server acknowledges it
  PUT /sessions/{id}/visual-signals, then POST /sessions/{id}/start with video.status

Backend (app/services/pipeline.py, _run() -- runs in this order)
  ... existing audio pipeline (transcribe, VAD, raw metrics, semantic analysis) ...
  _run_video_analysis           after semantic analysis, before the existing coaching stage
    visual_analysis.signals.prepare_signals    resample onto a uniform 10Hz grid
    visual_analysis.events.detect_events       7 event types from the prepared signals
    visual_analysis.metrics.compute_metrics    11-row metrics table, gated on coverage
    visual_analysis.pipeline.run_pipeline      assembles VideoAnalysisResult, stores it,
                                                upserts SessionMetric rows
  ... existing coaching stage (unchanged) ...
  _run_visual_coaching          after the existing coaching stage, only if video status
                                is "processed" or "partial"
    session_timeline.timeline.build_timeline       assembles the read-only SessionTimeline
                                                     from already-stored artifacts
    session_timeline.correlation.build_correlated_moments
                                                     5 rule-based moment candidates -> top 8
    visual_coaching.prompt      deterministic payload -- no raw metric value ever included
    visual_coaching.service     the one LLM call, JSON mode, one retry on a rule violation
    visual_coaching.validator   no digits/%/number-words, no affect words, known ids only
                                stores visual_feedback.json

Report UI (web/components/VisualDeliverySection.tsx, KeyMomentsList.tsx)
  Metrics table with confidence + plain definitions, gated on video_analysis_status
  Key moments: LLM coaching text where available, falls back to raw moment facts
  otherwise (a failed coaching pass never hides the underlying measurements)
```

## Module layout

```
visual_analysis/            Pure backend computation, no I/O.
  config.py                 Every threshold in one place. All provisional -- see below.
  schema.py                 Pydantic models: VisualSignalTrack and its nested shapes.
  signals.py                Validation beyond the schema; grid resampling; PreparedSignals.
  events.py                 7 event types from PreparedSignals.
  metrics.py                11-row metrics table from PreparedSignals + events.
  pipeline.py                run_pipeline(): signals -> events -> metrics -> VideoAnalysisResult.

session_timeline/           Pure, built from already-stored artifacts (not stored itself).
  timeline.py                SessionTimeline: words, speech_segments, pauses, fillers,
                              argument_units, visual_events, each mapped from its real source.
  correlation.py             The 5 correlation rules -> CorrelatedMoments.

visual_coaching/             The only package that calls an LLM in this feature.
  prompt.py                  Deterministic payload assembly + the system prompt.
  validator.py                Pydantic schema for the response + the 7 content rules.
  service.py                  Orchestrates timeline -> moments -> prompt -> LLM -> validate.

app/services/
  visual_signals.py           Ingest/validation/storage for VisualSignalTrack, plus
                               store/load for video_analysis.json and visual_feedback.json.
  pipeline.py                 _run_video_analysis / _run_visual_coaching: where the above
                               packages are wired into the existing session pipeline.

app/models/video_analysis.py  VideoAnalysis (one row per session) and SessionMetric
                               (one row per session per metric, for queryable history).

web/features/video-analysis/  Frontend capture: MediaPipe extraction, the adaptive
                               scheduler, pure math (head pose, iris offset, hand
                               assignment), the track builder, IndexedDB persistence,
                               upload with retry. useVisualCapture.ts is the orchestrating
                               hook; everything else is unit-testable pure TypeScript.

web/components/video-analysis/ ConsentPanel, SetupScreen (the framing/benchmark/
                                calibration/context UI shown before recording).

web/components/
  Recorder.tsx                 The existing recorder, extended with the opt-in path.
                                With the flag off or the user opted out, startRecording()/
                                submit() are byte-identical to the pre-existing code.
  VisualDeliverySection.tsx    Report UI: the metrics table + warnings + session-level notes.
  KeyMomentsList.tsx            Report UI: per-moment coaching, or raw facts if coaching failed.
```

## Schemas (source of truth)

- `VisualSignalTrack` (client -> server, schema `debatecoach.visual_signals` v1.0):
  `visual_analysis/schema.py`, mirrored in `web/features/video-analysis/types.ts`.
- `VideoAnalysisResult` (server, schema `debatecoach.video_analysis` v1.0): the dataclass
  in `visual_analysis/pipeline.py`, its `to_dict()` is the wire shape; mirrored in
  `web/lib/types.ts`'s `VideoAnalysisResult`.
- `visual_feedback.json` (the stored coaching document): assembled in
  `visual_coaching/service.py`, mirrored in `web/lib/types.ts`'s `VisualFeedbackDocument`.

Two status vocabularies exist for video analysis, deliberately different — do not treat
them as interchangeable:
- `VideoAnalysisResult.status`: `complete | partial | insufficient_data | unavailable | failed`
  (only `complete`/`partial`/`insufficient_data` are ever set by `run_pipeline` itself).
- `video_analyses.status` (the DB column, `VideoAnalysisStatus` in TypeScript):
  `not_requested | awaiting_upload | received | processing | processed | partial |
  insufficient_data | unavailable | failed`. `app/services/pipeline.py` translates the
  result's `"complete"` to the DB's `"processed"`; every other value passes through
  unchanged (see `_RESULT_STATUS_TO_DB_STATUS`).

## Configuration and tuning

Every threshold — coverage gates, the camera-facing cone, event durations, confidence
bands — lives in `visual_analysis/config.py` and `web/features/video-analysis/config.ts`,
with a comment on the module marking all of it provisional. None of it comes from labelled
data yet. See `THRESHOLD_TUNING.md` for the annotation format and the evaluation script
that turns hand-labelled sessions into precision/recall numbers per event type.

## Running the tests

```bash
# Backend (pytest.ini already points at tests/, pythonpath=.)
.venv/bin/pytest tests/ -q

# Frontend pure-TypeScript tests (Vitest, scoped to features/**/__tests__/**)
cd web && npm test
```

## The debug page

`web/app/dev/vision-debug/page.tsx` (route `/dev/vision-debug`) is available only when
`NODE_ENV !== "production"` or `NEXT_PUBLIC_VISION_DEBUG === "true"` — verified against a
real production build, where the route 404s. It shows live numeric readouts for every
derived field, the current device tier, effective fps, p90 latency, and an on-screen
checklist for verifying signs (§ below). It is never linked from production navigation.

## What still needs manual verification

Everything below was built against the MediaPipe documentation and verified numerically
in isolation (see the "Errors and Fixes" history in this feature's commits), but none of
it has been confirmed against a real camera and a real face yet. Do this before trusting
the feature with real users — see `MANUAL_TEST_PLAN.md` for the exact steps:

1. **Head-pose signs.** Turn your head to your right: `yaw` should increase. Look up:
   `pitch` should increase. Tilt your head to your right shoulder: `roll` should increase.
   If any is inverted, flip the corresponding constant in
   `web/features/video-analysis/math.ts` (`YAW_SIGN` / `PITCH_SIGN` / `ROLL_SIGN` —
   each is a single `1` or `-1`, isolated exactly so this fix is one line).
2. **Iris direction.** Look right with your eyes only (head still): `iris_x` should
   increase. Look up: `iris_y` should increase.
3. **Handedness.** Raise your right hand: `rh_present` should become `1`, not `lh_present`.
   The debug page's calibration step exercises the one-retry flip described in
   `web/features/video-analysis/math.ts`'s `resolveHandSideFromLabel`.
4. **Clock offset.** The clap test in `MANUAL_TEST_PLAN.md` measures the actual offset
   between the audio recorder's start event and the first usable video frame; if it's
   consistently non-zero, adjust `CLOCK_OFFSET_S` in
   `web/features/video-analysis/config.ts` (currently `0`).

## Regenerating MediaPipe assets

```bash
cd web && node scripts/setup-mediapipe.mjs
```

Idempotent; copies the WASM runtime from `node_modules/@mediapipe/tasks-vision/wasm/` and
downloads the two `.task` model files from Google's model CDN into `public/mediapipe/`,
writing a `manifest.json` with each file's sha256. Runs automatically on `npm install`
(wired as `postinstall`). `public/mediapipe/` is gitignored; nothing under it is committed.
If a download ever fails, the script stops rather than substituting a different URL.
