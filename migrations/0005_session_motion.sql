-- Practice motions: the motion a session was recorded against.
--
-- Not run automatically (see 0001's header). Run with plain psql:
--   psql "$DATABASE_URL" -v ON_ERROR_STOP=1 -f migrations/0005_session_motion.sql
-- IF NOT EXISTS, so a re-run is a no-op.
--
-- Apply BEFORE deploying the backend that uses it: the new backend's
-- ORM selects this column on every session query. The old backend
-- never touches it.

-- The ALTER needs a brief ACCESS EXCLUSIVE lock on sessions. Fail
-- fast rather than queue behind a long transaction (and block every
-- request queued behind us); re-run if it times out.
SET lock_timeout = '5s';

-- Nullable with no default, so Postgres adds it without rewriting the
-- table. NULL means "No prompt": every existing session, and every
-- new one recorded without a motion.
--
-- Holds an id from app/motions.py, the single source of truth for the
-- list. There is no foreign key (the list lives in code, not a table)
-- and no index (nothing filters sessions by motion). Ids are
-- permanent there; a motion is retired, never deleted, so a stored id
-- always resolves.
ALTER TABLE sessions
    ADD COLUMN IF NOT EXISTS motion_id varchar(64);

RESET lock_timeout;
