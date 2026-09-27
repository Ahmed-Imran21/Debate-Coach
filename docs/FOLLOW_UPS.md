# Follow-ups

Small, known issues that are not urgent. Each entry says what was
seen, why it is harmless for now, and what a fix would involve.

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
