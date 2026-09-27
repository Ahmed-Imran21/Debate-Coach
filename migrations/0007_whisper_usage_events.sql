-- Whisper (transcription) key usage for the admin dashboard.
--
-- Not run automatically (see 0001's header). A brand-new table and
-- index, so nothing existing is locked or rewritten; run it in one
-- transaction:
--   psql "$DATABASE_URL" -v ON_ERROR_STOP=1 -f migrations/0007_whisper_usage_events.sql
-- IF NOT EXISTS throughout, so a re-run is a no-op.
--
-- Apply BEFORE deploying the backend that writes it. The old backend
-- never touches it.
--
-- Why a new table and not key_usage: key_usage holds one row per key
-- with a single rolling 24h window and token columns. Whisper needs
-- two rolling windows at once (last hour and last 24 hours, the way
-- Groq enforces RPM/RPD and ASH/ASD), audio seconds instead of
-- tokens, failure and rate-limit counts, and a last-used time. One
-- row per attempt answers all of those with simple range queries.
-- key_usage and the LLM path are left exactly as they are.

BEGIN;

CREATE TABLE IF NOT EXISTS whisper_usage_events (
    id bigserial PRIMARY KEY,

    -- The key's id from api/whisper.py (e.g. "groq_whisper_large_v3_1"),
    -- never the key value.
    key_id varchar(128) NOT NULL,

    occurred_at timestamptz NOT NULL DEFAULT now(),

    -- Length of the audio sent. Counted toward "audio transcribed"
    -- only when outcome = 'ok'.
    audio_seconds double precision NOT NULL DEFAULT 0,

    -- Every attempt is recorded: a failed or rate-limited call still
    -- uses the key's request allowance.
    outcome varchar(16) NOT NULL CHECK (outcome IN ('ok', 'failed', 'rate_limited'))
);

-- Every dashboard figure is one key's rows in a recent time range.
CREATE INDEX IF NOT EXISTS ix_whisper_usage_events_key_time
    ON whisper_usage_events (key_id, occurred_at);

-- Rows older than 30 days are pruned by the application
-- (app/services/whisper_usage.py), so this stays small.

COMMIT;
