-- Progress graph: per-category scores on sessions, and the index
-- behind GET /v1/sessions/progress.
--
-- Not run automatically (see 0001's header). No BEGIN/COMMIT on
-- purpose: CREATE INDEX CONCURRENTLY can't run inside a transaction.
-- Run with plain psql, not --single-transaction:
--   psql "$DATABASE_URL" -v ON_ERROR_STOP=1 -f migrations/0003_session_category_scores.sql
-- Every statement is IF NOT EXISTS, so a partial run can simply be
-- re-run. (A CONCURRENTLY build that fails leaves an INVALID index
-- behind; drop it before re-running.)
--
-- Apply BEFORE deploying the backend that writes these columns:
-- the old backend never touches them, the new one needs them.

-- The ALTER needs a brief ACCESS EXCLUSIVE lock on sessions. Fail
-- fast rather than queue behind a long transaction (and block every
-- request queued behind us); re-run if it times out.
SET lock_timeout = '5s';

-- ------------------------------------------------------------
-- 1. Per-category scores
-- ------------------------------------------------------------
-- Until now these lived only in each session's feedback.json in
-- object storage, and the session list copied just overall_score.
-- Nullable with no default, so Postgres adds them without
-- rewriting the table. Written by the pipeline when coaching
-- completes; existing sessions are filled in by
-- scripts/backfill_category_scores.py. score_rebuttal stays NULL
-- when the speech had nothing to rebut ("not scored", not zero).

ALTER TABLE sessions
    ADD COLUMN IF NOT EXISTS score_argumentation double precision,
    ADD COLUMN IF NOT EXISTS score_rebuttal double precision,
    ADD COLUMN IF NOT EXISTS score_structure double precision,
    ADD COLUMN IF NOT EXISTS score_persuasion double precision,
    ADD COLUMN IF NOT EXISTS score_logic double precision;

RESET lock_timeout;

-- ------------------------------------------------------------
-- 2. Progress query
-- ------------------------------------------------------------
-- Every progress request is one user's completed sessions in a
-- created_at range (or the newest N by created_at): an index range
-- scan on this, never a scan of other users' rows.

CREATE INDEX CONCURRENTLY IF NOT EXISTS ix_sessions_user_status_created
    ON sessions (user_id, status, created_at);
