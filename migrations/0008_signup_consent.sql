-- Sign-up consent: when each user ticked the Privacy Policy and the
-- Terms and Conditions boxes at sign-up.
--
-- Not run automatically (see 0001's header). Run with plain psql:
--   psql "$DATABASE_URL" -v ON_ERROR_STOP=1 -f migrations/0008_signup_consent.sql
-- IF NOT EXISTS, so a re-run is a no-op.
--
-- Apply BEFORE deploying the backend that uses it: the new backend's
-- ORM selects these columns on every user query. The old backend
-- never touches them.

-- The ALTER needs a brief ACCESS EXCLUSIVE lock on users. Fail fast
-- rather than queue behind a long transaction (and block every
-- request queued behind us); re-run if it times out.
SET lock_timeout = '5s';

-- Nullable with no default, so Postgres adds them without rewriting
-- the table, and no existing row changes: NULL means the account
-- predates the boxes. Those users aren't asked again.
ALTER TABLE users
    ADD COLUMN IF NOT EXISTS privacy_policy_accepted_at timestamptz,
    ADD COLUMN IF NOT EXISTS terms_accepted_at timestamptz;

RESET lock_timeout;
