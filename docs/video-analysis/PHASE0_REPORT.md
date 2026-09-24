# Phase 0 report: inspection of the Debate Coach repository

Branch: `video-analysis` (clean, contains all work up to commit `49671c2`).
Inspection was read-only. No code was changed.

This report is organised so the decisions come first. Section 1 lists
the conflicts between the task document and the repository, each with
a recommendation. Section 2 is the name mapping. Sections 3 to 8 are the
inventory the document asked for. Section 9 is the file plan.

---

## 1. Conflicts with the task document, and the decisions they force

The document's "prior knowledge" is mostly real, but it describes a
**different backend from the one that is deployed**. Everything below
follows from that and from four things the document assumes exist but do
not: tests, migrations, JSON output mode, and an LLM retry mechanism.

### 1.1 Two backends exist; the document names the legacy one

| | deployed (`app/`) | legacy (`server/` + root `session.py`) |
|---|---|---|
| entry | `app/main.py` (`uvicorn app.main:app`, Dockerfile:71) | `server/app.py` |
| pipeline | `app/services/pipeline.py` | `server/pipeline.py` |
| concurrency | `app/services/jobs.py` (`ThreadPoolExecutor`) | `server/concurrency.py` |
| session record | `app/models/session.py` (SQLAlchemy, Postgres) | root `session.py` (filesystem dir), `session_manager.py` |
| object keys | `app/services/storage.build_object_key()` | `session.object_key_for()` |
| artifact upload | `pipeline.ARTIFACTS` + `_upload_artifacts()` (pipeline.py:66-72, 329-354) | `session.sync_artifacts_to_storage()` (boto3, different env vars) |
| status mapping | `SessionStatus` enum (app/models/session.py:13-33) | `session.to_backend_status()` |
| storage | Google Cloud Storage | S3-compatible via `STORAGE_*` env (dead config) |

The Dockerfile ships `api/ audio/ raw_metrics/ speech_analysis/ coaching_engine/ app/`
and nothing else. Nothing under `app/` or `api/` imports `server/`,
`session.py`, or `session_manager.py`. The legacy path is the CLI
(`main.py`) plus an older HTTP server that predates the current one.

**Decision:** all backend work targets `app/`. The legacy path is left
untouched. Every `[verify]` reference to `server/*`, `session_manager.py`,
`object_key_for()`, `sync_artifacts_to_storage()`, `to_backend_status()`
maps to the `app/` equivalents in the table above.

### 1.2 The §2.1.6 "known mismatch" does not exist

The document asks me to confirm that `audio/transcriber.py` nests words
inside segments while `delivery_metrics.py` expects a flat list.

- `audio/transcriber.py:84-95` writes `"segments": result.segments`, and
  each segment carries `"words": [...]` (`api/whisper.py:1015-1050`).
- All three consumers read the nested shape:
  `raw_metrics/metrics.py:21`, `raw_metrics/filler_detector.py:54`,
  `raw_metrics/stutter_detector.py:37` — each is `segment.get("words", [])`.
- No module anywhere reads a top-level `words` list (grep is empty).
- The legacy `server/pipeline.py:5` imports the same `transcribe_audio`,
  so local and server pipelines produce the same transcript shape, and
  both take VAD from the same `audio/audio_analyzer.py`.

The shapes are consistent. The defect the document is probably
remembering was different: until earlier on this branch,
`api/whisper.py` read segments with `getattr()` on plain dicts, which
made every segment's `start`/`end` `None` and its `words` empty. That
is fixed (`_field`, `_normalize_words`, `_attach_loose_words`).

**Decision needed (§2.2 scope).** Prerequisite A as written replaces a
mismatch that isn't there. Its remaining value is real: a global word
index, `segment_id` on every word, and `word_range` on every segment
are exactly what Phase 5 needs for excerpts and what Prerequisite B
needs for time anchoring. Two ways to get it:

- **A1 (recommended): additive.** Keep `transcription.json` exactly as
  it is (nested words). Add one pure function
  `audio/transcript_shape.py::to_canonical(transcription) -> CanonicalTranscript`
  that produces the document's `{words, segments}` shape in memory, with
  `text` stripped (raw words arrive as `" We"`, with a leading space).
  Call it once in `app/services/pipeline.py` after transcription and
  hand the result to the new argument-unit step and to
  `session_timeline`. `raw_metrics/` is not touched, so there is nothing
  to keep numerically identical, and stored artifacts from existing
  sessions keep loading.
- **A2: as specified.** Change the stored shape and rewrite the three
  `raw_metrics` consumers. Higher risk, no tests to prove equivalence,
  and every session already in Cloud Storage would have the old shape.

Speech-activity shape needs no work: `analysis.json` already has
`speech_segments: [{start, end, duration}]` and `pauses` in seconds
(`audio/audio_analyzer.py:224-234`). The canonical
`speech_segments: [{start, end}]` is a view over it.

### 1.3 Argument units carry no IDs (Prerequisite B is real work)

`speech_analysis/speech_analyzer.py:39-63` sends the LLM lines shaped
`[0.90 - 7.36] text`. The prompt (`speech_analysis/llm/prompts.py`)
tells the model to *write* `start`, `end` and the exact `text` itself.
Output units have no segment IDs and no index into the transcript;
alignment today would be by float comparison (unsafe: the stored
transcript has `0.9000000000000004`, the prompt shows `0.90`) or text
matching. Segments must also be chronological and non-overlapping
(`response_parser.validate_segment_order`, :61-86).

The real taxonomy (`speech_analysis/llm/schemas.py:9-21`) is eleven
labels: `claim, argument, evidence, example, reasoning, rebuttal,
counterargument, concession, logical_fallacy, conclusion, question`. A
unit may carry several. The document's key units (`claim`, `rebuttal`,
`conclusion`) exist verbatim. Mapping for the document's five-way
taxonomy: `claim -> claim|argument`, `evidence -> evidence|example|reasoning`,
`rebuttal -> rebuttal|counterargument`, `conclusion -> conclusion`,
`other -> concession|logical_fallacy|question`. `logical_fallacy` stays
as a label since the coaching rules and the report's `SpeechTrack` read
it.

Consumers that must keep working: `coaching_engine/utils/validators.py:76-83`
requires `{start, end, text, labels}` on every segment, and five
coaching prompts embed `speech_content.json` verbatim. Plan: add
`id`, `segment_ids` and keep every existing field; compute `start`/`end`
deterministically from the referenced transcript segments and write
those over the LLM's values.

### 1.4 There is no JSON output mode (§0.3 rule 2 vs rule 9)

Neither provider requests structured output:
`api/providers/groq.py:29-44` never sets `response_format`;
`api/providers/gemini.py:38-61` never sets `response_mime_type`. The
coaching engine strips code fences by hand (`engine.py:88-105`) and its
`response_schema` argument is type-checked then dropped
(`coaching_engine/llm/client.py:62-65`, never forwarded). Validation is
Pydantic (`speech_analysis`) or an inline required-keys check
(`coaching_engine/llm/parser.py:71-90`). There is no shared helper.

Rule 2 says "use the existing pattern"; there is none. Rule 9 says do
not modify the key registry, rate limiter, or rotation code. Adding
JSON mode means threading one optional argument through
`APIClient.generate` (`api/client.py:151`) and into the two providers.
`api/client.py` is the gateway, not one of the protected modules
(`scheduler.py`, `rate_limiter.py`, `key_registry.py`,
`request_queue.py`, `queue_worker.py`, `usage_tracker.py`,
`whisper.py`), but it is adjacent.

**Decision needed:**
- **J1 (recommended):** add an optional `response_format` passthrough to
  `APIClient.generate` -> `GroqProvider.generate` (`response_format={"type":"json_object"}`)
  and `GeminiProvider.generate` (`response_mime_type="application/json"`).
  Additive, default `None`, no change to scheduling or limits. Use it
  for the new argument-unit prompt and the visual coaching call only;
  existing coaching calls are left as they are.
- **J2:** no JSON mode; rely on the validator. Weaker, and contradicts
  rule 2's intent.

### 1.5 There is no migration mechanism (§0.5 mandatory stop)

Schema is created by `Base.metadata.create_all()` in the lifespan
(`app/main.py:32`). Alembic is in `requirements.txt:27` but there is no
`alembic.ini`, no versions directory, and no deploy step. `create_all`
creates **new** tables but never adds columns to existing ones. The
document's §3.5 adds three columns to `sessions`; against the live Cloud
SQL database those would silently not exist and every session write
would fail.

**Decision needed:**
- **M1 (recommended):** do not alter `sessions`. Put all new state in
  the new `video_analyses` table (`status`, `unavailable_reason`,
  `coaching_status`, keys) and derive `video_analysis_status` for the
  API from that row (absent row = `not_requested`). `create_all` creates
  new tables safely. No migration needed for this feature.
- **M2:** wire up Alembic properly (baseline from current models, one
  migration, `alembic upgrade head` as a Cloud Build step before
  deploy). Correct long-term, but it is a deployment change outside
  this feature and needs its own approval.

Either way, session deletion already removes the storage prefix
(`app/routes/sessions.py:349-379` calls `storage.delete_prefix`) so new
artifacts under the same prefix are covered; new rows need
`ondelete="CASCADE"` plus an ORM relationship with `passive_deletes=True`
so `db.delete(debate_session)` does not try to null the FK first.
**There is no account-deletion endpoint** (`users.py` has only
`GET /users/me`), so §3.5's "account deletion must remove" has nothing
to extend; noted as an open item.

### 1.6 There are no tests, anywhere

Backend: no `tests/`, no `conftest.py`, no `pytest.ini`/`pyproject.toml`,
no `pytest` in requirements. No fixtures named strong/weak/mixed (the
only hits are prose inside coaching prompts). Frontend: no test runner,
no test files. The document's gates "existing test suite passes" and
"existing delivery-metric tests must produce the same numbers" are
vacuous.

**Plan:** add `pytest` (backend) and Vitest (frontend, pure TS only, per
§4.13). Before Prerequisite B changes the prompt, write one
characterisation test that runs `raw_metrics.analyze_metrics` on a
committed synthetic `transcription.json` + `analysis.json` and pins the
numbers, so A1's "nothing changed" claim is checkable. The local
`sessions/session_*` directories contain real recordings and are
correctly untracked (`.gitignore:1-2`); they must not become fixtures.

### 1.7 There is no LLM retry mechanism (§7.1, §7.5)

`api/providers/*` do not retry (their docstrings say so). `APIClient`
executes once; a 429 sets a cooldown on that key and returns failure.
The only "retry" is capacity wait in `queue_worker.py`. §7.5's
"retry the whole call once" is therefore a new behaviour.

**Decision:** implement it as a second plain `generate()` call inside
`visual_coaching/service.py` when the validator rejects items, not as a
generic mechanism. This adds nothing to `api/`.

### 1.8 Smaller conflicts

- **No finalize endpoint.** The lifecycle is `POST /v1/sessions` (create,
  returns presigned PUT) -> client PUTs audio -> `POST /v1/sessions/{id}/start`.
  `start` has no request body today. §3.6's optional `video` object goes
  on `start`. Absent body keeps today's behaviour.
- **Signal upload transport.** The audio path is presigned-PUT because
  audio is large. A presigned PUT for signals would bypass the §3.3
  server-side validation and gzip-bomb cap at upload time. Recommend a
  direct `PUT /v1/sessions/{id}/visual-signals` (body cap 2 MB) that
  validates and then stores via `storage.upload_bytes`. Flagging because
  §3.6 says "match repo style".
- **`Permissions-Policy: camera=()`** (`web/next.config.mjs:44`)
  currently forbids camera access. Must become `camera=(self)`. CSP
  `script-src` needs `'wasm-unsafe-eval'`. `worker-src` is not needed for
  the main-thread implementation in §4.5.
- **No `web/public/` directory** exists; it must be created for WASM and
  models. No MediaPipe dependency is installed.
- **No `onstart` listener and no `timeslice`** on the recorder
  (`web/components/Recorder.tsx:124-172`). §4.6 adds an `onstart`
  listener; the existing `startedAt = Date.now()` at :166 is set *before*
  `recorder.start()` and is display-only.
- **Feature flags:** none exist. `Settings` (`app/core/config.py`) is
  pydantic-settings, snake_case, read from env/`.env`. New:
  `video_analysis_enabled: bool = False` ->
  `VIDEO_ANALYSIS_ENABLED`. Frontend: `NEXT_PUBLIC_VIDEO_ANALYSIS_ENABLED`.
- **Repo hygiene (not touching without approval):** `backend/` is a
  tracked stale copy of the app; `web/{app` is an untracked empty dir
  from a failed brace-expansion `mkdir`; `sessions copy/.gitkeep` and
  `README copy.md` are tracked leftovers. None affect the plan.

---

## 2. Name mapping: document -> repository

| Document says | Repository has | Notes |
|---|---|---|
| `server/app.py` | `app/main.py` | `server/app.py` exists but is legacy |
| `server/pipeline.py` | `app/services/pipeline.py` | |
| `server/concurrency.py` | `app/services/jobs.py` | |
| `session.py`, `session_manager.py` | `app/models/session.py` (`DebateSession`), `app/routes/sessions.py` | root files are legacy CLI |
| `object_key_for()` | `app/services/storage.build_object_key()` (:66-71) | `users/{user_id}/sessions/{session_id}/{filename}` |
| `sync_artifacts_to_storage()` | `pipeline.ARTIFACTS` (:66-72) + `_upload_artifacts()` (:329-354) | each artifact has a `*_object_key` column |
| `to_backend_status()` | `SessionStatus` enum + `PIPELINE_STAGES` (app/models/session.py:13-44) | progress = index / 7 |
| `audio/transcriber.py` | same (real, in the live path) | wraps `api/whisper.WhisperClient` |
| `debate_analysis/delivery_metrics.py` | `raw_metrics/metrics.py` (+ `filler_detector.py`, `stutter_detector.py`) | |
| `debate_analysis/preprocessing.py` | `app/services/audio_convert.py` (ffmpeg -> 16 kHz mono WAV) | |
| `debate_analysis/semantic_analysis.py` | `speech_analysis/speech_analyzer.py` + `speech_analysis/llm/` | |
| `debate_analysis/coaching.py` | `coaching_engine/engine.py` (`CoachingEngine`) | |
| `feedback_aggregator.py` | `coaching_engine/qualitative_feedback/feedback_aggregator.py` | do not feed visual metrics into it |
| `api/key_registry.py`, `rate_limiter.py` | `api/key_registry.py`, `api/rate_limiter.py` (+ `scheduler.py`, `request_queue.py`, `queue_worker.py`, `usage_tracker.py`, `whisper.py`) | protected set |
| "the existing LLM client" | `api/client.APIClient.generate(task, estimated_tokens, provider, model, messages, ...)` via process-wide `app/services/engine.py` | |
| "existing schema-key validation helper" | none shared; `coaching_engine/llm/parser.py:71-90` inline | new one goes in `visual_coaching/validator.py` |
| "finalize" | `POST /v1/sessions/{id}/start` | |
| strong / weak / mixed fixtures | none | |
| Supabase / RLS | not applicable: Cloud SQL Postgres, JWT auth in `app/routes/deps.py`, ownership in `_get_owned_session()` | |
| Cloudflare R2 | Google Cloud Storage (`google-cloud-storage`) | |

---

## 3. Frontend (`web/`)

- Next.js **15.5.25, App Router**, React 19.0.0, TypeScript 5.7.3 strict.
  Dependencies are exactly `next`, `react`, `react-dom`; dev:
  `@types/*`, `eslint`, `eslint-config-next`, `typescript`. No UI
  library, no state library, no test runner, no ESLint config file, no
  Prettier. Path alias `@/*` -> `web/`.
- Recording (`components/Recorder.tsx`, client component):
  `getUserMedia({ audio: true })` at :113; `pickMimeType()` tries
  `audio/webm;codecs=opus`, `audio/webm`, `audio/mp4`, `audio/ogg;codecs=opus`
  (:19-30); `new MediaRecorder(stream, { mimeType })` (:124);
  `recorder.start()` with **no timeslice** (:172); `ondataavailable`
  pushes chunks, `onstop` builds `new Blob(chunks, { type: mimeType })`
  and calls `teardown()` (:127-135). `teardown` (:60-78) stops **all**
  tracks via `getTracks()`, closes the `AudioContext` used for the level
  meter, and runs on unmount. **No `onstart` handler exists.** Duration
  is wall-clock for display only.
- Upload (`lib/api.ts:235-262`): `createSession({content_type, title})`
  -> `fetch(upload_url, {method:"PUT", headers: upload_headers, body})`
  -> `startSession(id)`. Single presigned PUT; no retry/backoff; codec
  params stripped from `content_type`. `request()` replays once on 401
  after refresh; no other retry.
- Report (`app/practice/[id]/page.tsx`): polls every 4 s; renders
  overall score, WPM, speaking time, filler/pause/stutter counts,
  `SpeechTrack` (inline SVG timeline with pause/filler/stutter/fallacy
  marks), six category bars, filterable findings.
  **Audio playback exists**: `report.audio_url` -> `<audio controls>`
  (:340-351). The `<audio>` is not wired to the track; a seek-to button
  is feasible. Transcript text is not rendered.
- State: React local state only. `localStorage` keys `dc.access`,
  `dc.refresh`. No preferences store -> use `dc.videoAnalysisOptIn`.
- CSP (`next.config.mjs:14-32`): `default-src 'self'; script-src 'self' 'unsafe-inline'; ... connect-src 'self' <api> <storage>; media-src 'self' blob: https:`.
  `Permissions-Policy: camera=(), geolocation=(), microphone=(self)` (:44).
- Design tokens (`app/globals.css:12-38`): `--paper`, `--paper-raised`,
  `--well`, `--rule`, `--rule-strong`, `--ink`, `--ink-soft`,
  `--ink-faint`, `--pine`, `--pine-deep`, `--brick`, `--amber`,
  `--radius 3px`, `--step-0..5`. Fonts via `next/font/google`
  (self-hosted at build): Newsreader (`--font-serif`), IBM Plex Sans
  (`--font-sans`). Conventions: `.btn`, `.btn-quiet`, `.btn-sm`,
  `data-tone="danger|failed|done"`, `.figures/.figure`, `.bars/.bar-row`,
  `.findings/.finding[data-severity]`, `.note`, `.lede`, `.alert`,
  `.defs`, `.steps`, `.split`.

## 4. Backend (`app/`)

- Entry `app/main.py`; lifespan runs `create_all`, ffmpeg check,
  `engine.start()` (one `APIClient`), `jobs.start(max_workers)`.
- `DebateSession` (`app/models/session.py`): `id`, `user_id` (FK cascade),
  `title`, `status` (enum), seven `*_object_key` String(512) columns
  (`upload`, `audio`, `transcription`, `analysis`, `raw_metrics`,
  `speech_content`, `coaching`), `queue_wait_seconds`, `overall_score`,
  `duration_seconds`, `words_per_minute`, `feedback_count`,
  `error_message`, `extra` (JSONB; pipeline writes `extra["llm_errors"]`),
  timestamps. `progress` property from `PIPELINE_STAGES`.
- Status set: `created, queued, converting, transcribing, analyzing_audio, calculating_metrics, analyzing_speech, coaching, completed, failed`.
  Video must not add to this (progress divisor is `len(PIPELINE_STAGES)`).
- Auth: JWT (`app/core/security.py`), `get_current_user` in
  `app/routes/deps.py`, ownership via `_get_owned_session()` returning
  404 for other users' sessions (`routes/sessions.py:32-51`).
- Deletion: `DELETE /v1/sessions/{id}` -> 409 if running, else
  `storage.delete_prefix(users/{uid}/sessions/{sid}/)` + `db.delete`.
- Storage: GCS, presigned V4 URLs signed via self-impersonation on
  Cloud Run (`app/services/storage.py`). `upload_bytes`, `upload_json`,
  `upload_file`, `download_*`, `delete_prefix` exist.
- Database: Cloud SQL Postgres via SQLAlchemy 2 + pg8000 through the
  Cloud SQL connector; `create_all` only (see 1.5).
- Pipeline (`app/services/pipeline.py:_run`, :137-322), tempdir per run:

| status | writes | line |
|---|---|---|
| converting | `recording.wav` (16 kHz mono) | :170-215 |
| transcribing | `transcription.json` | :222-231 |
| analyzing_audio | `analysis.json` (VAD) | :237-243 |
| calculating_metrics | `raw_metrics.json` | :249-254 |
| analyzing_speech | `speech_content.json` | :260-267 |
| coaching | `feedback.json` | :273-290 |
| (publish) | uploads `ARTIFACTS`, records summary | :305-316 |

  **Hook point:** transcript, VAD, raw metrics and argument units are
  all on disk after `analyze_speech()` returns at :267, before
  `mark(SessionStatus.coaching)` at :273. Visual analysis and the
  timeline run there; visual coaching runs after the existing coaching
  at :290 (§7.1). The original upload is deleted at :201, which is
  irrelevant here because no video is ever uploaded.

## 5. Audio analysis shapes

- `transcription.json` (`audio/transcriber.py:84-95`):
  `{session_id, audio_file, language, language_probability, whisper_api_key_id, segments:[{start, end, text, words:[{word, start, end, probability}]}]}`.
  Words are nested; word text keeps a leading space; `probability` is
  `None` from Groq. `WhisperResult.text` is not persisted.
- `analysis.json` (`audio/audio_analyzer.py:224-234`): Silero VAD at
  16 kHz, `min_speech_duration_ms=250`, `min_silence_duration_ms=300`,
  default threshold. `{total_duration, speech_duration, silence_duration, speech_percentage, speech_segments:[{start,end,duration}], pauses:[{start,end,duration}]}`
  in seconds. Pauses are gaps between speech segments only.
- `raw_metrics.json` (`raw_metrics/metrics.py:96-120`):
  `speech{total_duration, speech_duration, silence_duration, speech_percentage, word_count, words_per_minute}`,
  `pauses{count, total_duration, average_duration, longest_duration}` (summary only),
  `fillers{count, words{}, instances[{word|phrase, start, end}]}`,
  `stutters{count, instances[{type, text, start, end}]}`.
  For the timeline, per-pause intervals come from `analysis.json`, per
  filler/stutter from `raw_metrics.json` instances.
- `speech_content.json` (`speech_analysis/models/speech_content.py`):
  `{session_id, segments:[{start, end, text, labels[], fallacy_type?}]}`.

## 6. LLM layer

- `APIClient.generate()` picks a key by capacity score across providers
  filtered by optional `provider`/`model`; blocks on the queue when no
  capacity. Groq path requires `messages`; Gemini path requires
  `prompt`. Model id comes from the key (`openai/gpt-oss-120b`,
  `llama-3.3-70b-versatile`, `gemini-2.5-flash`), configured by
  `api/config.KEY_CONFIGS`.
- Semantic analysis: groq `openai/gpt-oss-120b`, `temperature=0.0`,
  `max_tokens=4000`, Pydantic validation, raises on failure.
- Coaching: five calls (one per category), `temperature=0.2`,
  `max_tokens=2500`, code-fence stripping, inline validation, failures
  swallowed into `extra["llm_errors"]`.
- No JSON mode, no shared validator, no retry (see 1.4, 1.7). The
  visual coaching call will use the same provider/model selection as
  coaching (`task="visual_coaching"`).

## 7. Tests

None (see 1.6).

## 8. Confirmed absences the document should know about

- No `web/public/`, no MediaPipe, no test runners, no ESLint config.
- No account-deletion endpoint.
- No `alembic/` directory despite the dependency.
- No JSON output mode on either provider.

---

## 9. File plan

Every backend path is under the deployed tree. Names follow the
document's suggestions where the repo has no stronger convention.

### Modified

| File | Why |
|---|---|
| `app/core/config.py` | `video_analysis_enabled: bool = False` |
| `app/models/session.py` | ORM relationship to `video_analyses` (M1) or new columns (M2) |
| `app/schemas/session.py` | additive: `video_analysis` on create, `video` on start, result fields |
| `app/routes/sessions.py` | accept the new fields; new `PUT /{id}/visual-signals`; flag gating |
| `app/services/pipeline.py` | call `to_canonical()`; run visual pipeline + timeline after :267; visual coaching after :290; new `ARTIFACTS` rows |
| `speech_analysis/speech_analyzer.py` | `prepare_transcript` emits `[s_004] text`; compute unit `start`/`end` from segment ids |
| `speech_analysis/llm/prompts.py`, `llm/schemas.py`, `llm/response_parser.py`, `models/speech_content.py` | `id`, `segment_ids`; drop unknown ids; keep every existing field |
| `api/client.py`, `api/providers/groq.py`, `api/providers/gemini.py` | optional `response_format` passthrough (J1) |
| `requirements.txt` | `pytest`; `numpy` already present |
| `web/next.config.mjs` | `camera=(self)`; `'wasm-unsafe-eval'` |
| `web/components/Recorder.tsx` | opt-in gate; add video track only when opted in; audio-only `MediaStream` to the recorder; `onstart` t0; stop video tracks |
| `web/lib/api.ts`, `web/lib/types.ts` | additive fields and the signal upload call |
| `web/app/practice/[id]/page.tsx` | "Visual delivery" and "Key moments" sections; seek button on the existing `<audio>` |
| `web/app/privacy/page.tsx` | camera/measurement/MediaPipe paragraph, `LEGAL REVIEW REQUIRED` |
| `web/package.json`, `web/.gitignore` | pinned `@mediapipe/tasks-vision`, Vitest, `setup-mediapipe` script, ignore downloaded models |

### New

| File | Why |
|---|---|
| `audio/transcript_shape.py` | `to_canonical()` (Prerequisite A, option A1) |
| `visual_analysis/{__init__,config,schema,signals,metrics,events,pipeline}.py` | §3, §5, pure |
| `session_timeline/{__init__,timeline,correlation}.py` | §6, pure |
| `visual_coaching/{__init__,prompt,validator,service}.py` | §7 |
| `app/models/video_analysis.py`, `app/models/session_metric.py` | §3.5 tables |
| `app/services/visual_signals.py` | I/O glue: decompress with cap, validate, store |
| `tests/conftest.py`, `tests/test_raw_metrics_characterisation.py`, `tests/visual_analysis/*`, `tests/session_timeline/*`, `tests/visual_coaching/*`, `tests/api/test_visual_signals.py` | §3.7, §5.8, §6.3, §7.6 |
| `web/features/video-analysis/{consent,extractor,math,scheduler,track,storage,upload}.ts` (+ components) | §4; pure math files have no DOM/MediaPipe imports |
| `web/public/mediapipe/{wasm,models,manifest.json}` | §4.1 (models fetched at build, gitignored) |
| `web/scripts/setup-mediapipe.mjs` | §4.1 |
| `web/app/dev/vision-debug/page.tsx` | §4.12 |
| `web/vitest.config.ts`, `web/features/video-analysis/__tests__/*` | §4.13 |
| `scripts/evaluate_visual_events.py` | §11 |
| `docs/video-analysis/{README,MANUAL_TEST_PLAN,THRESHOLD_TUNING}.md` | §11 |

### Not touched

`api/{scheduler,rate_limiter,key_registry,request_queue,queue_worker,usage_tracker,whisper}.py`,
`coaching_engine/**` (including `feedback_aggregator.py`),
`raw_metrics/**` (under A1), `audio/audio_analyzer.py`, `server/**`,
root `session.py`/`session_manager.py`/`main.py`, `backend/**`.

---

## 10. Decisions I need from you before writing code

1. **A1 or A2** for the canonical transcript shape (1.2). I recommend A1.
2. **J1 or J2** for JSON output mode (1.4). I recommend J1.
3. **M1 or M2** for the database (1.5). I recommend M1 for this feature.
4. **Signal upload transport**: direct authenticated `PUT` through the API (recommended) or presigned PUT to GCS with deferred validation.
5. Confirm the taxonomy mapping in 1.3, in particular that `argument` counts as a claim-type key unit and that `logical_fallacy` stays a label rather than becoming a unit type.
6. Whether I may commit this report now (`video-analysis(phase-0): inspection report`) or hold it until the Phase 0 code commit.

---

## 11. Decisions (approved)

1. **Backend target:** all work targets `app/`. `server/`, root `session.py`
   and `session_manager.py` are legacy: not modified, not imported, not
   deleted. Every document reference is translated via §2.
2. **Prerequisite A:** additive. One normalization function builds the
   canonical shape in memory at the point transcription enters analysis.
   Stored `transcription.json` and all `raw_metrics` consumers unchanged.
   Characterization tests pin current `raw_metrics` output first. Every
   transcription fallback is confirmed to yield the nested shape, or the
   normalizer handles it with a test. New code reads only the canonical
   shape.
3. **Prerequisite B:** units reference segment ids; code computes
   `start`/`end`; LLM timestamps are no longer used for placement.
   Characterization test of current argument-analysis structure (mocked
   LLM) first. Every field existing consumers read is kept. Commit message
   lists the 11-label to key-unit mapping.
4. **JSON output mode:** optional `response_format` passthrough in
   `api/client.py`, default `None`; mapped to each provider's native JSON
   mode. Key registry, rotation and rate limiting untouched. Used only by
   the visual coaching call and the Prerequisite B semantic call. Existing
   coaching is not retrofitted. Fence-stripping stays as a fallback parser.
   **Known issue:** `coaching_engine/llm/client.py:62-65` accepts a
   `response_schema` argument and silently drops it.
5. **Database:** no changes to existing tables. New tables only
   (`video_analyses`, one row per session that requested video, created at
   `POST /start`; `session_metrics`). No row = `not_requested`.
   `ON DELETE CASCADE` on FKs to `sessions`. Ownership enforced in every
   new route and proven by tests. **Tech debt:** introduce Alembic with a
   baseline migration.
6. **Tests:** pytest (backend), Vitest (pure frontend TS only), minimal
   config. "Existing tests must pass" means the characterization tests
   pass before and after each change. Fixtures are generated JSON only.
7. **API flow:** the finalize contract moves to `POST /start`. The client
   completes audio upload and signal upload before calling it. Absent
   `video` field = today's behaviour. `uploaded` with no stored track = 409.
8. **Permissions-Policy:** `camera=()` becomes `camera=(self)` in
   `web/next.config.mjs`; nothing else changes.
9. **LLM retry:** no general mechanism. Only the single validator-driven
   retry in visual coaching. Failure sets `visual_coaching_status = failed`;
   metrics and moments still display.
10. This report is the first commit on the branch.
