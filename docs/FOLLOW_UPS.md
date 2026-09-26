# Follow-ups

Small, known issues that are not urgent. Each entry says what was
seen, why it is harmless for now, and what a fix would involve.

## passlib logs a bcrypt traceback on the first password hash

**Seen:** Cloud Run logs an ERROR-severity traceback once per
container, on the first login or signup after a cold start:

```
File ".../passlib/handlers/bcrypt.py", line 620, in _load_backend_mixin
    version = _bcrypt.__about__.__version__
AttributeError: module 'bcrypt' has no attribute '__about__'
```

It was logged on revision `debate-coach-backend-00017-cir`
(2026-09-24, 2026-09-25) and again on `00020-ruy` (2026-09-26), so
it predates the feedback-synthesis and progress-graph deploy.

**Why it's harmless:** passlib 1.7.4 (`requirements.txt`:
`passlib~=1.7.4`) reads the bcrypt version from
`bcrypt.__about__`, which bcrypt removed in 4.1 (`bcrypt~=4.2.0`
here). passlib catches the error, logs it, and carries on; hashing
and verification work. The login that triggered the 2026-09-26
entry succeeded.

**Cost:** noise. It's an ERROR in the logs after every cold start,
which makes real errors harder to spot and would trip any
alert on ERROR severity.

**Fix options:**

1. Replace passlib with direct `bcrypt.hashpw` / `bcrypt.checkpw`
   calls. passlib is unmaintained. Existing `$2b$` hashes verify
   unchanged. One catch: bcrypt 4.1+ raises `ValueError` for
   passwords over 72 bytes, where passlib silently truncated, and
   signup allows up to 128 characters (`app/schemas/auth.py`). The
   replacement must truncate to 72 bytes the same way, or existing
   long passwords stop verifying. Test that explicitly.
2. Pin `bcrypt<4.1`. This is quick but holds back a security-relevant
   dependency.
3. Silence the `passlib.handlers.bcrypt` logger. This hides the
   symptom only.

Option 1 is the recommended fix, with a test for a >72-byte password
hashed by the current code still verifying afterwards.

## An expired tab keeps sending heartbeats that get 401 every minute

**Seen:** one browser tab (Firefox on Ubuntu) has sent
`POST /v1/users/heartbeat` every minute since 2026-09-24 18:07 UTC,
and every one gets a 401. It never redirects to login and never
stops.

**Likely cause (frontend):** `web/components/Heartbeat.tsx` runs a
60-second interval that fires whenever *any* access token is in
localStorage, expired or not. `heartbeat()` in `web/lib/api.ts` uses
`retryOnAuthFailure: false` on purpose, so a forgotten tab can't
keep a session alive forever by refreshing. The interval then
swallows the 401 (`.catch(() => {})`), so nothing ever stops it.

**Why it's harmless:** the design goal holds: the session does
expire, and the requests are rejected. The cost is one wasted
request per minute per forgotten tab, log noise, and a tab that
still looks signed in until the next real action.

**Fix direction (not done):** on a 401 from heartbeat, clear the
interval, or stop pinging while the stored access token is past
its `exp` (`tokenExpiresAt` in `web/lib/jwt.ts` already decodes it).
Keep `retryOnAuthFailure: false`: the heartbeat must not refresh.
Whether to also redirect to login, or leave that to the next real
action, is a UX call.
