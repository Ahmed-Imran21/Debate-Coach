-- AI progress report: one stored report per user per UTC day.
--
-- Not run automatically (see 0001's header). A brand-new table, so
-- nothing existing is locked or rewritten; run it in one
-- transaction:
--   psql "$DATABASE_URL" -v ON_ERROR_STOP=1 -f migrations/0004_progress_reports.sql
-- IF NOT EXISTS throughout, so a re-run is a no-op.
--
-- Apply BEFORE deploying the backend that uses it. The old backend
-- never touches this table.

BEGIN;

CREATE TABLE IF NOT EXISTS progress_reports (
    id uuid PRIMARY KEY,

    -- Deleting an account (self-delete or admin force-delete) removes
    -- its reports with it, like every other per-user table.
    user_id uuid NOT NULL REFERENCES users (id) ON DELETE CASCADE,

    -- The UTC calendar day the report was generated on. The unique
    -- constraint below IS the once-per-day limit: two generations
    -- finishing at the same moment (a double click, two tabs) can't
    -- both be stored, whatever the application checked beforehand.
    -- A row is only ever written after the LLM call succeeded, so a
    -- failed attempt never uses up the day.
    report_date date NOT NULL,
    created_at timestamptz NOT NULL DEFAULT now(),

    -- N the user asked for, and how many completed sessions actually
    -- existed and were used (fewer than N is allowed; fewer than 2
    -- never reaches the LLM, so never produces a row).
    session_count_requested integer NOT NULL CHECK (session_count_requested IN (3, 5, 7)),
    session_count_used integer NOT NULL CHECK (session_count_used BETWEEN 2 AND 7),

    -- The sessions compared, oldest first, and the report itself:
    -- {"bullets": ["...", ...]}, at most 5.
    session_ids jsonb NOT NULL,
    content jsonb NOT NULL,

    model varchar(64) NOT NULL,
    prompt_version varchar(64) NOT NULL,

    -- Also serves GET /latest (one user's rows, newest day first).
    CONSTRAINT uq_progress_reports_user_day UNIQUE (user_id, report_date)
);

COMMIT;
