# Follow-ups

Small, known issues that are not urgent. Each entry says what was
seen, why it is harmless for now, and what a fix would involve.

## An intermittent backend test failure, not yet identified

**Seen:** 2026-09-26, on the feature/practice-prompts branch. One of
nine full backend test runs had a single failure; the other eight
passed. The failing test's name wasn't captured, because the output
was filtered to the summary line before anyone looked. One suspicion,
unconfirmed: the local dev backend was reloading on file edits at the
time, and its cleanup job runs against the same local Postgres
database that the real-Postgres tests use.

**Tried to reproduce:** 2026-09-27, on fix/follow-ups. 20 full
backend runs in a row (`pytest tests/ -q -o addopts="" -rf`,
unfiltered), with the local dev backend running under `--reload` and
the local Postgres up: all 20 passed (646 tests each, no failures or
errors). Nothing in the repo was edited during those runs, so a
reload happening mid-run was not exercised. Left open, since the
cause was never seen.

**Next time:** record the failing test's name and full output before
rerunning (`pytest -rf`, and don't filter the output). Then rerun that
test alone, and again with the local backend stopped.
