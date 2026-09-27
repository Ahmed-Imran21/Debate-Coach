-- Shareable read-only report links.
--
-- Not run automatically (see 0001's header). A brand-new table and
-- its indexes, so nothing existing is locked or rewritten; run it in
-- one transaction:
--   psql "$DATABASE_URL" -v ON_ERROR_STOP=1 -f migrations/0006_session_shares.sql
-- IF NOT EXISTS throughout, so a re-run is a no-op.
--
-- Apply BEFORE deploying the backend that uses it (the session list
-- reads it to mark shared sessions). The old backend never touches it.

BEGIN;

CREATE TABLE IF NOT EXISTS session_shares (
    id uuid PRIMARY KEY,

    -- Deleting the session, or the account (which deletes its
    -- sessions), deletes its links: the link is permanently dead.
    session_id uuid NOT NULL REFERENCES sessions (id) ON DELETE CASCADE,

    -- SHA-256 (hex) of the link token. The token itself is never
    -- stored: it's shown to the owner once, when the link is created.
    -- It's 32 random bytes from secrets.token_urlsafe, never derived
    -- from the session id. Unique: the public lookup is by this hash.
    token_hash char(64) NOT NULL UNIQUE,

    created_at timestamptz NOT NULL DEFAULT now(),

    -- Set by "Stop sharing" or "Create new link". A revoked row never
    -- matches a lookup again.
    revoked_at timestamptz
);

-- At most one active link per session. Also serves "is this session
-- shared?" lookups for the owner's report page and session list.
CREATE UNIQUE INDEX IF NOT EXISTS uq_session_shares_one_active
    ON session_shares (session_id)
    WHERE revoked_at IS NULL;

COMMIT;
