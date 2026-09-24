-- Admin user management: indexes for GET /v1/admin/users.
--
-- Not run automatically (see 0001's header). No BEGIN/COMMIT on
-- purpose: CREATE INDEX CONCURRENTLY can't run inside a transaction,
-- and it's what keeps these from locking the users table while they
-- build. Run with plain psql, not --single-transaction:
--   psql "$DATABASE_URL" -v ON_ERROR_STOP=1 -f migrations/0002_admin_user_management.sql
-- Every statement is IF NOT EXISTS, so a partial run can simply be
-- re-run. (A CONCURRENTLY build that fails leaves an INVALID index
-- behind; drop it before re-running.)

-- ------------------------------------------------------------
-- 1. Keyset pagination
-- ------------------------------------------------------------
-- Each matches one sort's ORDER BY exactly, so the next page is an
-- index range scan from the cursor — no OFFSET, no sort step, the
-- same cost on page 1 as on page 1,000.

-- sort=newest: ORDER BY created_at DESC, id DESC
CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_users_created_at_id
    ON users (created_at DESC, id DESC);

-- sort=last_seen: ORDER BY last_seen_at DESC NULLS LAST, id DESC
-- (0001's idx_users_last_seen_at stays: it serves the dashboard's
-- "active now" range count.)
CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_users_last_seen_at_id
    ON users (last_seen_at DESC NULLS LAST, id DESC);

-- ------------------------------------------------------------
-- 2. Substring search
-- ------------------------------------------------------------
-- search matches "%term%" anywhere in email, first_name or last_name.
-- A btree index can't serve a leading wildcard; a trigram GIN index
-- can, including ILIKE (pg_trgm folds case itself).
--
-- One index over the three fields joined, not one per field: with
-- three per-column indexes the planner priced the OR of all three
-- above a full scan and never used them (measured on 50,000 users:
-- 70 ms sequential scan). Searching the joined text uses this index
-- in ~2 ms, and also lets a full name ("jane doe") match across the
-- first/last boundary. The query in app/services/admin_users.py must
-- use exactly this expression or the index won't match.
-- Terms under 3 characters are too short for trigrams and scan.
-- On Cloud SQL, CREATE EXTENSION needs the cloudsqlsuperuser role;
-- locally pg_trgm is a trusted extension the database owner can add.

CREATE EXTENSION IF NOT EXISTS pg_trgm;

CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_users_search_trgm
    ON users USING gin ((email || ' ' || first_name || ' ' || last_name) gin_trgm_ops);

-- ------------------------------------------------------------
-- 3. Per-page session counts
-- ------------------------------------------------------------
-- session_count is counted only for the rows on the current page,
-- through this index. It already exists wherever create_all() built
-- the sessions table (the model declares index=True); this is a
-- no-op there and a safety net anywhere it doesn't.
CREATE INDEX CONCURRENTLY IF NOT EXISTS ix_sessions_user_id
    ON sessions (user_id);
