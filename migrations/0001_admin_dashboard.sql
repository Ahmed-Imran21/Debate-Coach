-- Admin dashboard: active-user tracking + persisted API key usage.
--
-- Not run automatically. Base.metadata.create_all() (app/main.py's
-- startup path) only creates tables that don't exist yet — it never
-- alters an existing one, so the new "users" column below needs a
-- real migration. This is the first schema change on this project
-- that does (see docs/video-analysis/README.md's "Known tech debt:
-- no real migration mechanism" for the earlier, additive-only case).
-- key_usage itself is a new table and would be picked up by
-- create_all() on its own, but it's included here so both pieces of
-- this feature's schema land together in one reviewable step.
--
-- Run directly, e.g.:
--   psql "$DATABASE_URL" -f migrations/0001_admin_dashboard.sql

BEGIN;

-- ------------------------------------------------------------
-- 1. users.last_seen_at
-- ------------------------------------------------------------
-- Nullable: existing users have no meaningful "last seen" until
-- their next authenticated request touches it. No backfill.

ALTER TABLE users
    ADD COLUMN last_seen_at timestamptz;

-- Serves "active now" (count(*) where last_seen_at > now() - '5
-- minutes'), which scans this column directly.
CREATE INDEX idx_users_last_seen_at ON users (last_seen_at);

-- ------------------------------------------------------------
-- 2. key_usage
-- ------------------------------------------------------------
-- One row per API key identifier from api/key_registry.py (e.g.
-- "groq_gpt_oss_120b_1", matching APIKey.id's exact format from
-- api/config.py::load_api_keys() — lowercased KEY_CONFIGS name +
-- "_" + the .env KEY_<n> suffix). Rows are seeded/upserted by the
-- application, not this migration; the natural key IS the primary
-- key since the set of keys is config-driven, not user data.
--
-- display_label and the soft request/token limits are NOT stored
-- here — they live in application config (next step), so changing
-- a label or a limit is a code change, not a migration.
--
-- Counts are the primary numbers (self-tracked from real API
-- responses, not estimated). last_rate_limit_headers is supplementary
-- only, per the provider's own rate-limit headers when present —
-- Gemini generally doesn't return the standard-style headers Groq
-- does, so this will be null for most Gemini rows in practice.
--
-- window_start / window_reset_at hold ONE window per row, matching
-- each provider's real daily-scale limit (rpd/tpd in APILimits) —
-- not also a per-minute window; per-minute enforcement stays
-- entirely in api/rate_limiter.py's existing in-memory tracking,
-- untouched by this table. How window_reset_at gets computed differs
-- by provider (application logic, not this migration):
--   groq:   rolling — window_start + 24h, rolled forward whenever
--           the window lapses (Groq's own reset-* headers express a
--           duration until refill, not a fixed clock time).
--   gemini: fixed — the next literal midnight Pacific Time, in UTC
--           (Google's documented quota reset for the Generative
--           Language API; not UTC midnight).

CREATE TABLE key_usage (
    key_id                    text PRIMARY KEY,
    provider                  text NOT NULL,

    request_count              integer NOT NULL DEFAULT 0,
    prompt_tokens              integer NOT NULL DEFAULT 0,
    completion_tokens          integer NOT NULL DEFAULT 0,
    total_tokens               integer NOT NULL DEFAULT 0,

    window_start              timestamptz NOT NULL DEFAULT now(),
    window_reset_at           timestamptz NOT NULL,

    -- Latest snapshot only, overwritten each call that returns any
    -- (e.g. {"x-ratelimit-remaining-requests": "27", ...}).
    last_rate_limit_headers   jsonb,

    created_at                timestamptz NOT NULL DEFAULT now(),
    updated_at                timestamptz NOT NULL DEFAULT now()
);

COMMIT;
