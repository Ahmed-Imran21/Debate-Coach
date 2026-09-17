# What's new on `video-analysis`

Comparison base: **`web-platform`** (there's no `web-development` branch in this repo;
`web-platform` is the branch `video-analysis` actually forked from — its tip, `49671c2`,
is the exact merge-base between the two). If a `web-development` branch exists elsewhere
and isn't pushed here, let me know and I'll re-diff against that instead.

**100 files changed: 76 new, 24 modified (23 substantive + a `package-lock.json` dependency
bump), +15,657 / -221 lines, across 18 commits.**

This document is a snapshot as of branch tip `3bc7f12`. It is not meant to be kept in
sync with the code going forward — `docs/video-analysis/README.md` is the living
architecture reference; this file is a one-time "what changed" summary.

---

## 1. What the feature does

An optional, camera-based delivery-analysis add-on to Debate Coach. When a user opts in,
their browser runs on-device computer vision (MediaPipe) on the camera feed during a
recording — measuring head direction, whether they're facing the camera, and hand
movement — and discards every frame immediately after extracting ~17 numbers from it. Only
those numbers are ever sent to the server. The backend correlates them with the argument
structure the existing audio pipeline already produces, generates a short list of
"moments" worth commenting on, and makes one separate LLM call to turn those into plain
coaching prose — with a deterministic validator guaranteeing the model never states a
number, percentage, or emotional/character judgment. The report page gets a new "Visual
delivery" section and a "Key moments" list.

**With both feature flags off, the application is byte-identical to before this branch
existed.** No new network requests, no MediaPipe download, no new required fields.

## 2. Feature flags

| Flag | Where | Default |
|---|---|---|
| `VIDEO_ANALYSIS_ENABLED` | `app/core/config.py` (backend) | `false` |
| `NEXT_PUBLIC_VIDEO_ANALYSIS_ENABLED` | `web/.env.example` (frontend) | unset/false |

Both must be on for any part of the feature to activate.

## 3. Safety properties (verified, not just intended)

- **No video/frame/image/landmark ever leaves the browser.** Only derived numeric
  signals. Verified: no `toDataURL`/`toBlob` anywhere in the capture code (grepped, only
  a comment documenting the absence); the MediaPipe WASM/model bundle (~155KB) lands in
  its own lazy chunk absent from every route's eager bundle (confirmed by inspecting a
  real `next build` output).
- **No emotion/character inference anywhere** — enforced by the visual-coaching
  validator's affect-word blocklist, applied to every LLM output before storage.
- **Deterministic-vs-LLM split** — every countable number (angles, durations, ratios,
  counts) is computed in plain Python. The LLM prompt (`visual_coaching/prompt.py`) never
  contains a raw metric value; only status, confidence, and pre-bucketed plain-English
  descriptions (e.g. a duration becomes "brief"/"sustained"/"long", never "4.2s").
- **A video failure never fails a session.** Both new pipeline stages
  (`_run_video_analysis`, `_run_visual_coaching`) catch every exception internally and
  degrade their own status field; the audio/transcript/coaching pipeline is untouched.
- **Deletion**: session delete already removes every new storage object (it deletes by
  the session's whole object-key prefix, which every new artifact lives under) and the
  two new DB tables cascade-delete at the database level via their existing foreign
  keys — no code changes were needed for either.

## 4. Data flow

```
Browser (opted in)
  Setup screen: framing checks, benchmark, gaze calibration, right-hand calibration, context
  Recording: MediaPipe Face Landmarker + Hand Landmarker, ~10fps adaptive
  Each analyzed frame -> ~17 derived numbers -> frame discarded immediately
  VisualSignalTrack (gzipped JSON) held in IndexedDB until the server acknowledges it

Backend session pipeline (app/services/pipeline.py, run in this order)
  ... existing audio pipeline: transcribe, VAD, raw metrics, semantic analysis ...
  NEW: _run_video_analysis        (after semantic analysis, before existing coaching)
    -> visual_analysis: prepare_signals -> detect_events -> compute_metrics -> run_pipeline
    -> stores video_analysis.json, upserts SessionMetric rows
  ... existing coaching stage (completely unchanged) ...
  NEW: _run_visual_coaching       (after existing coaching, only if video status allows)
    -> session_timeline: build_timeline -> build_correlated_moments (top 8, by salience)
    -> visual_coaching: build the no-raw-numbers prompt -> one LLM call (JSON mode)
       -> validate (7 rules) -> retry once on violation -> drop what still fails
    -> stores visual_feedback.json

Report UI
  VisualDeliverySection: metrics table + warnings, gated on video_analysis_status
  KeyMomentsList: LLM coaching text per moment, or raw computed facts if coaching failed
```

## 5. New backend packages

### `visual_analysis/` — pure computation, no I/O
| File | What it does |
|---|---|
| `config.py` | Every threshold in one place (coverage gates, the facing cone, event durations, confidence bands, rounding). All explicitly marked provisional. |
| `schema.py` | Pydantic models for `VisualSignalTrack` (the client→server contract) — strict, versioned (`debatecoach.visual_signals` v1.0). |
| `signals.py` | Validation beyond the schema (§3.3 rules with stable error codes); `prepare_signals()` resamples raw frames onto a uniform 10Hz grid (interpolation, gap-masking, smoothing) into a `PreparedSignals` object. |
| `events.py` | `detect_events()`: the 7 event types (`gaze_away`, `head_down`, `gesture`, `hands_still`, `face_lost`, `second_person`, `analysis_degraded`) from `PreparedSignals`. |
| `metrics.py` | `compute_metrics()`: the 11-row metrics table (face/camera-facing/gaze/head/hand/gesture measures), each gated on coverage with a real status enum (`ok`/`insufficient_coverage`/`not_measured`/`disabled_by_tier`). |
| `pipeline.py` | `run_pipeline()`: assembles the full `VideoAnalysisResult` (status, quality summary, metrics, events, a 1Hz chart-ready series) from a track + speech segments. |

### `session_timeline/` — pure, built from already-stored artifacts
| File | What it does |
|---|---|
| `timeline.py` | `build_timeline()`: a read-only `SessionTimeline` assembled from transcript words, speech segments, pauses, fillers, argument units, and visual events — each mapped from its real stored source. |
| `correlation.py` | `build_correlated_moments()`: the 5 rule-based correlation rules pairing visual events with "key" argument units (claim/rebuttal/conclusion), salience-scored, deduplicated, capped at 8. |

### `visual_coaching/` — the only package that calls an LLM in this feature
| File | What it does |
|---|---|
| `prompt.py` | Builds the LLM input payload and system prompt. Converts every number to a status/confidence/bucketed description before it's sent. |
| `validator.py` | Pydantic schema for the response shape + the 7 content rules (allowed categories/polarities, known IDs only, no digits/%/number-words, no affect words, no em dash/emoji, max 6 items). |
| `service.py` | Orchestrates: build timeline → correlate moments → build prompt → call the LLM (same provider/model as the existing coaching engine) → validate → retry once on a violation → return the document to store. |

### `audio/transcript_shape.py` (new, but shared infrastructure from Phase 0)
One canonical transcript shape (`CanonicalWord`/`CanonicalSegment`/`CanonicalTranscript`)
used by everything downstream — session timeline, correlation, excerpt-building. Doesn't
change what's stored on disk; it's a pure in-memory view.

### New database tables (`app/models/video_analysis.py`)
- **`video_analyses`** — one row per session: status, unavailable reason, coaching
  status, schema/metrics versions, a `quality` JSONB summary, and storage keys for the
  signal track / result / feedback documents.
- **`session_metrics`** — one row per session per metric (value, unit, coverage,
  confidence, status), unique on `(session_id, metric_key, definition_version)`, indexed
  for per-user metric history queries.

Both are additive-only: no existing table was altered (the deployed schema is created by
`Base.metadata.create_all()`, which only adds new tables).

## 6. New/changed API surface

- `POST /sessions` — accepts an optional `video_analysis: "requested" | "not_requested"`.
- `PUT /sessions/{id}/visual-signals` — new route; validates, stores the signal track.
- `POST /sessions/{id}/start` — accepts an optional `video: {status, reason}` body.
  **Backward compatible**: a request with no `video` field behaves exactly as before.
- Session/report responses gain (all additive, all null/omitted when the flag is off):
  `video_analysis_status`, `video_unavailable_reason`, `visual_coaching_status`,
  `video_analysis`, `correlated_moments`, `visual_feedback`.

With `VIDEO_ANALYSIS_ENABLED` off: the signal-upload route 404s, session creation ignores
`video_analysis`, and responses omit/null the new fields.

## 7. Modified existing backend files, and why

| File | Change |
|---|---|
| `api/client.py`, `api/providers/{groq,gemini}.py` | Added an optional `response_format="json"` passthrough (inert unless a caller opts in) — used by the visual-coaching LLM call. |
| `app/core/config.py` | Added `video_analysis_enabled`. |
| `app/models/__init__.py` | Registers the two new models so `create_all()` picks them up. |
| `app/routes/sessions.py` | The API surface changes in §6 above. |
| `app/schemas/session.py` | New request/response fields, all additive. |
| `app/services/pipeline.py` | The two new pipeline stages (`_run_video_analysis`, `_run_visual_coaching`) plus `_record_session_metrics`; `_run_video_analysis` now returns its result dict instead of `None` so the second stage can reuse it without a redundant storage round-trip. |
| `speech_analysis/*` (5 files) | Prerequisite B: argument units are now identified by transcript segment IDs (never LLM-written timestamps), computed deterministically from canonical segments. Existing coaching behavior preserved — fields were added, not removed. |

## 8. New frontend capture feature (`web/features/video-analysis/`)

Pure, unit-tested TypeScript with no DOM/MediaPipe imports (so it's testable without a
browser), orchestrated by one hook:

| File | What it does |
|---|---|
| `config.ts` | Every frontend constant (target fps, scheduler thresholds, calibration/benchmark thresholds, upload retry delays, IndexedDB max age). |
| `math.ts` | Head pose from the MediaPipe rotation matrix, iris offset, face scale/center, palm centroid, hand-side assignment. |
| `scheduler.ts` | `AdaptiveScheduler` — downgrade-only frame-rate/hand-tracking throttling based on measured latency; never upgrades mid-recording. |
| `stats.ts` | `percentile90`, `median`, `meanAbsoluteDeviation`. |
| `framing.ts` | Distance/lighting classification, face-visible/hands-raised pass checks for the setup screen. |
| `track.ts` | `TrackBuilder` — enforces strictly-increasing timestamps, rounds every column to the schema's precision, manages gaps. |
| `types.ts` | TypeScript mirror of the backend's Pydantic schema. |
| `consent.ts` | Opt-in choice persistence (`localStorage`). |
| `storage.ts` | IndexedDB wrapper: save/load/delete/cleanup-old-tracks. |
| `extractor.ts` | `MediaPipeExtractor` — GPU-with-one-CPU-retry model loading, dynamically imported only after opt-in. |
| `upload.ts` | Gzip-if-supported upload with exponential backoff. |
| `useVisualCapture.ts` | The orchestrating hook: the frame loop, mode-gated accumulation (benchmark/calibration/recording), framing checks, face-missing timer, tab-visibility gap tracking. |

Plus `web/scripts/setup-mediapipe.mjs` (idempotent, wired as `postinstall`): copies the
WASM runtime and downloads the two model files from Google's model CDN into
`public/mediapipe/` (gitignored, never committed), writing a manifest with each file's
sha256. Models are always served same-origin, never from a CDN at runtime.

## 9. New frontend UI

- `web/components/video-analysis/ConsentPanel.tsx`, `SetupScreen.tsx` — the opt-in panel
  and the framing → benchmark → gaze calibration → hand calibration → context step
  sequence shown before recording.
- `web/app/dev/vision-debug/` — a dev-only debug page (confirmed 404 in a real production
  build) with live readouts of every derived signal, for verifying head-pose signs and
  handedness against a real camera.
- `web/components/VisualDeliverySection.tsx` — the report page's metrics table
  (label, formatted value, confidence pill, one-line definition), grouped
  not-ok-metric messages, warnings, and session-level coaching notes.
- `web/components/KeyMomentsList.tsx` — per-moment coaching text with a "play from here"
  seek button on the existing audio player; falls back to showing the raw computed facts
  (no coaching prose) if the coaching LLM call failed, so a coaching failure never hides
  the underlying measurements.

## 10. Modified existing frontend files, and why

| File | Change |
|---|---|
| `web/components/Recorder.tsx` | Extended with the full opt-in path (consent → setup → recording → finalize). With the flag off or the user opted out, the recording/submit code path is byte-identical to before. |
| `web/lib/api.ts` | `request()` gained a raw-body mode for the gzipped track upload; `createSession`/`startSession` exported with additive video params; new `uploadVisualSignals()`. |
| `web/lib/types.ts` | New types for every video-analysis shape (`VideoAnalysisResult`, `VisualMetric`, `VisualEvent`, `CorrelatedMoment`, `VisualFeedbackItem`/`Document`) plus their UI label/formatting constants. |
| `web/app/practice/[id]/page.tsx` | Wires in the two new report sections and an audio-seek callback. |
| `web/app/privacy/page.tsx` | New "Camera-based delivery analysis" section and a MediaPipe processor entry, both marked `LEGAL REVIEW REQUIRED`. |
| `web/next.config.mjs` | CSP gained `'wasm-unsafe-eval'`; `Permissions-Policy` changed from forbidding camera access (`camera=()`) to allowing it same-origin (`camera=(self)`). |
| `web/.env.example`, `web/.gitignore` | New env var documented; `public/mediapipe/` gitignored. |

## 11. Testing

- **210 backend tests** (`pytest`), all passing, covering: schema validation, the gzip
  decompression cap (tested against a real gzip bomb via `tracemalloc`), signal
  preparation math, every event type with hand-derived exact-value assertions, every
  metric's gating/confidence logic, the full result envelope, all 5 correlation rules
  and their selection mechanics, the coaching validator's 7 rules, and both pipeline
  hooks end-to-end against a fake-storage/SQLite harness.
- **77 frontend tests** (Vitest), covering the pure math/scheduler/stats/framing/track
  modules — plus a cross-language fixture written by a frontend test and independently
  validated by a backend test, proving both sides agree on the wire format.
- `scripts/evaluate_visual_events.py` — precision/recall/mean-IoU evaluation against
  hand-labelled ground truth, for tuning the (currently provisional) thresholds once
  real recordings exist.

## 12. New documentation

- `docs/video-analysis/PHASE0_REPORT.md` — the original inspection report and your
  approved decisions (the binding contract this whole branch was built against).
- `docs/video-analysis/README.md` — architecture/data-flow/module reference.
- `docs/video-analysis/MANUAL_TEST_PLAN.md` — sign verification, the clap-test clock-offset
  procedure, browser matrix, lighting/framing/second-person/offline scenarios.
- `docs/video-analysis/THRESHOLD_TUNING.md` — the labelling format and how to use the
  evaluation script.

## 13. Judgment calls worth knowing about

- **One real correction mid-build**: `visual_analysis/metrics.py` and `pipeline.py` were
  initially reconstructed from architecture alone (the source spec had scrolled out of
  context) and were substantively wrong — rewritten from scratch once the spec was
  re-shared (commit `ea868c8`). `signals.py` and `events.py`, built earlier with the
  spec in hand, needed no changes.
- The LLM prompt's bucketing phrases (duration/facing/fraction descriptions) and the
  report UI's metric labels/definitions are my own wording, matched to the one or two
  verbatim examples the spec gives — not literally specified for every case.

## 14. Still needs manual verification (nothing here can be checked by an automated test)

- Head-pose signs, iris direction, handedness mapping — built against MediaPipe's
  documentation and verified numerically in isolation, never against a real face.
- Clock offset between audio and video timestamps (the clap-test procedure).
- The full opt-in → setup → record → upload → analyze → coach → report flow, clicked
  through in a real browser — this environment has no browser tool, so nothing has
  literally been watched running as a user would see it.

Full detail on all of the above, with exact fix locations if something's wrong, is in
`docs/video-analysis/MANUAL_TEST_PLAN.md`.
