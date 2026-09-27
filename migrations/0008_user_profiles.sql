-- Profile page: username, bio, weekly goal and time zone, plus a
-- cache of each session's Delivery score for personal bests.
--
-- Not run automatically (see 0001's header). Two brand-new tables and
-- their indexes, so nothing existing is locked, rewritten or changed;
-- run it in one transaction:
--   psql "$DATABASE_URL" -v ON_ERROR_STOP=1 -f migrations/0008_user_profiles.sql
-- IF NOT EXISTS throughout, so a re-run is a no-op.
--
-- Apply BEFORE deploying the backend that uses it. The old backend
-- never touches either table.

BEGIN;

-- ------------------------------------------------------------
-- 1. user_profiles: one optional row per user
-- ------------------------------------------------------------
-- A separate table rather than new columns on users, so the users
-- table (and every existing query, admin view and export of it) is
-- untouched, and the username and bio can't leak into anything that
-- reads users. No row means every default: no username, no bio, a
-- weekly goal of 3, no stored time zone. The row is created the
-- first time the user saves anything on /profile.

CREATE TABLE IF NOT EXISTS user_profiles (
    -- Deleting the account deletes the profile.
    user_id uuid PRIMARY KEY REFERENCES users (id) ON DELETE CASCADE,

    -- Optional. Stored lowercase: 3 to 20 lowercase letters, digits
    -- or underscores (the API lowercases input before checking).
    username varchar(20)
        CONSTRAINT user_profiles_username_format CHECK (username ~ '^[a-z0-9_]{3,20}$'),

    -- Optional plain text, up to 160 characters (varchar counts
    -- characters, not bytes). Line breaks are kept.
    bio varchar(160),

    -- Completed sessions per Monday-to-Sunday week.
    weekly_goal smallint NOT NULL DEFAULT 3
        CONSTRAINT user_profiles_weekly_goal_range CHECK (weekly_goal BETWEEN 1 AND 7),

    -- IANA name from the browser (e.g. "Asia/Karachi"), so streak
    -- days and weeks follow the user's own midnight. NULL until the
    -- profile page first reports it; UTC is used until then.
    time_zone varchar(64),

    updated_at timestamptz NOT NULL DEFAULT now()
);

-- Usernames are unique case-insensitively. Stored values are already
-- lowercase; indexing lower() makes the database itself enforce it
-- whatever writes the row. NULLs (no username) never conflict.
CREATE UNIQUE INDEX IF NOT EXISTS uq_user_profiles_username_lower
    ON user_profiles (lower(username));

-- ------------------------------------------------------------
-- 2. session_delivery_scores: cache for personal bests
-- ------------------------------------------------------------
-- The Delivery (quantitative) score exists only inside each session's
-- feedback.json in object storage; unlike the other categories it was
-- never copied to a sessions column (0003). Rather than add a column
-- and backfill existing session rows, the profile endpoint reads a
-- completed session's feedback.json once, the first time it needs it,
-- and stores the score here. Existing rows are never modified.

CREATE TABLE IF NOT EXISTS session_delivery_scores (
    -- Deleting the session (or the account) deletes its cached score,
    -- so personal bests follow deletions.
    session_id uuid PRIMARY KEY REFERENCES sessions (id) ON DELETE CASCADE,

    -- 0-100, or NULL when the session's feedback.json has no usable
    -- Delivery score (never counted, never treated as zero).
    score double precision
        CONSTRAINT session_delivery_scores_range CHECK (score IS NULL OR (score >= 0 AND score <= 100)),

    created_at timestamptz NOT NULL DEFAULT now()
);

COMMIT;
