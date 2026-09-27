# Follow-ups

Small, known issues that are not urgent. Each entry says what was
seen, why it is harmless for now, and what a fix would involve.

## An expired tab keeps sending heartbeats that get 401 every minute

**Seen:** one browser tab (Firefox on Ubuntu) has sent
`POST /v1/users/heartbeat` every minute since 2026-09-24 18:07 UTC,
and every one gets a 401. It never redirects to login and never
stops.

**Likely cause (frontend):** `web/components/Heartbeat.tsx` runs a
60-second interval that fires whenever *any* access token is in
localStorage, expired or not. `heartbeat()` in `web/lib/api.ts` uses
`retryOnAuthFailure: false` on purpose, so a forgotten tab can't
keep a session alive forever by refreshing. The interval then
swallows the 401 (`.catch(() => {})`), so nothing ever stops it.

**Why it's harmless:** the design goal holds: the session does
expire, and the requests are rejected. The cost is one wasted
request per minute per forgotten tab, log noise, and a tab that
still looks signed in until the next real action.

**Fix direction (not done):** on a 401 from heartbeat, clear the
interval, or stop pinging while the stored access token is past
its `exp` (`tokenExpiresAt` in `web/lib/jwt.ts` already decodes it).
Keep `retryOnAuthFailure: false`: the heartbeat must not refresh.
Whether to also redirect to login, or leave that to the next real
action, is a UX call.

## Coaching score noise can look like a trend in a progress report

**Seen:** on the Feature 2 canary (2026-09-26), the same recording
was run through the pipeline twice. Rebuttal and logic came back a
level apart, 60 then 40, with nothing different in the speech. The
progress report then described both as having "slipped", which is
faithful to the scores but reports noise as a trend. The same
one-level wobble showed up in earlier calibration runs (the space
speech's rebuttal scored 40/60/40 across three runs).

**Why it matters:** a report over only 2 sessions compares two
single samples, so a one-level move can easily be scoring variance
rather than a real change.

**Options (not done):**
1. In `progress_report/prompt.py` (`_level_trends`), only call a
   level trend when it moves two or more levels, or moves in a
   consistent direction across three or more sessions. Otherwise
   report it as "about the same".
2. Reduce the variance at the source: in the coaching engine
   (`coaching_engine/llm/prompts.py`), for example with a lower
   temperature or more tightly anchored rubric levels. Re-verify
   calibration afterwards.

Either change needs real test runs, like the earlier calibration work.

## The first request after idle can take about 27 seconds

**Seen:** 2026-09-26 07:40 UTC. The backend had scaled to zero; a
`/health` request took 27.0s while a new instance started (startup
completed 07:40:57), and every request after answered in about 4ms.

**Why it matters:** the frontend's default request timeout is 30s
(`DEFAULT_TIMEOUT_MS` in `web/lib/api.ts`). A slightly slower cold
start, or a heavier first request, would fail with a timeout for the
first visitor after an idle period. The progress-report call has its
own 120s timeout, so it isn't affected.

**Options (not done):**
1. `--min-instances=1` on the Cloud Run service. This removes cold
   starts at the cost of one always-on instance.
2. A longer timeout, or one automatic retry, for the first request a
   page makes, so a cold start costs a delay instead of an error.

## The rule-based fallback ignores the practice motion

**Seen:** 2026-09-26, while testing practice motions. One of six
coaching runs got two responses missing part of the rubric in a row,
so the engine fell back to the deterministic rule modules. Those can't
read a motion, so a speech recorded against an unrelated motion (the
space-debate recording against the carbon-tax motion) got no
off-topic feedback, and it was scored as if no motion had been set.

**Why it matters:** the report shows the motion, so the user expects
coaching against it. On the fallback path they silently don't get it.
Fallbacks are rare (a double missing-rubric response, or the LLM
being unavailable), but they happen.

**Options (not done):**
1. Show a note on the report when a motion was set but coaching fell
   back. The pipeline already records `llm_errors` in the session's
   `extra`.
2. Add a simple deterministic relevance check to the fallback, for
   example keyword overlap between the motion and the transcript, that
   adds one "may not address the motion" item. It's cheap, but crude:
   it has to stay conservative to avoid false alarms.

## An intermittent backend test failure, not yet identified

**Seen:** 2026-09-26, on the feature/practice-prompts branch. One of
nine full backend test runs had a single failure; the other eight
passed. The failing test's name wasn't captured, because the output
was filtered to the summary line before anyone looked. One suspicion,
unconfirmed: the local dev backend was reloading on file edits at the
time, and its cleanup job runs against the same local Postgres
database that the real-Postgres tests use.

**Next time:** record the failing test's name and full output before
rerunning (`pytest -rf`, and don't filter the output). Then rerun that
test alone, and again with the local backend stopped.
