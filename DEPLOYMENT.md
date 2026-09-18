# Deployment

Backend on Cloud Run, database on Cloud SQL (Postgres 15), object
storage on Cloud Storage, frontend on Vercel.

- Project: `debate-coach-508804`
- Region: `us-central1`

## 1. Prerequisites

```bash
# Install/update the gcloud CLI, then:
gcloud auth login
gcloud config set project debate-coach-508804
```

## 2. Create GCP resources

Runs once per environment: enables APIs, creates the Cloud
Storage bucket, the Artifact Registry repository, the Cloud SQL
instance/database/user, and grants the runtime service account
the roles it needs.

```bash
./setup-gcp.sh
```

You'll be prompted for a database password. At the end it prints
the values you need for the next step — copy them somewhere safe
(the password isn't stored anywhere by the script).

## 3. Configure environment variables

```bash
cp .env.example .env.production
```

Fill in `.env.production` with:
- The GCP values `setup-gcp.sh` printed (`GCP_PROJECT_ID`,
  `GCP_STORAGE_BUCKET`, `GCP_SERVICE_ACCOUNT_EMAIL`,
  `CLOUD_SQL_CONNECTION_NAME`, `DB_USER`, `DB_PASSWORD`, `DB_NAME`)
- `JWT_SECRET_KEY` — generate one with `openssl rand -hex 32`
- Your existing `GROQ_*` / `GEMINI_*` keys
- `ALLOWED_ORIGINS` — your Vercel frontend URL (see step 5), plus
  `http://localhost:3000` if you still want local frontend dev to
  work against the deployed backend

Leave `DATABASE_URL` blank — `CLOUD_SQL_CONNECTION_NAME` takes
priority (see `app/db/database.py`).

`.env.production` holds real secrets. Do not commit it; it should
already be covered by `.gitignore`'s `.env*` pattern — confirm
before your first commit.

## 4. First backend deploy (Cloud Run)

```bash
gcloud builds submit --config cloudbuild.yaml \
  --substitutions=_ENV_VARS_FILE=.env.production
```

This builds the image, pushes it to Artifact Registry, and
deploys it to Cloud Run with the Cloud SQL instance attached.
When it finishes, grab the service URL:

```bash
gcloud run services describe debate-coach-backend \
  --region us-central1 \
  --format='value(status.url)'
```

Sanity-check it:

```bash
curl https://<your-service-url>/health
```

### Redeploying

Same command as above — `cloudbuild.yaml` always builds and
redeploys `latest`. For a quick config-only change (e.g. new env
var) without a rebuild:

```bash
gcloud run services update debate-coach-backend \
  --region us-central1 \
  --update-env-vars KEY=value
```

## 5. Frontend deploy (Vercel)

In the Vercel project settings for `web/`, set:

```
NEXT_PUBLIC_API_URL=https://<your-cloud-run-service-url>
NEXT_PUBLIC_STORAGE_ORIGIN=https://storage.googleapis.com
NEXT_PUBLIC_SITE_URL=https://<your-vercel-domain>
```

Then deploy as usual (`vercel --prod`, or push to the connected
branch).

Once you have the real Vercel URL, add it to `ALLOWED_ORIGINS` in
`.env.production` and redeploy the backend (step 4) so CORS
allows requests from it.

## 6. Verify end-to-end

1. Open the deployed frontend, sign up / log in.
2. Record or upload a session; confirm the upload reaches Cloud
   Storage (`gcloud storage ls gs://debate-coach-508804-recordings/users/`).
3. Confirm the session's report loads once processing finishes.
4. Check Cloud Run logs for errors:
   ```bash
   gcloud run services logs read debate-coach-backend --region us-central1
   ```

## Local development setup

Running the whole app locally against your own Postgres and your own
isolated GCS bucket — never the production database or bucket.
Everything below was verified working end-to-end while setting up a
fresh checkout.

**Prerequisites** (not covered below — install/arrange these first):
- `gcloud` CLI installed and authenticated as an account with access
  to the `debate-coach-508804` project (`gcloud auth login`). Section
  3's one-time bucket/service-account creation needs IAM admin rights
  on the project; if those already exist (they do, as of this
  writing — see Section 3), you only need enough access to be
  granted impersonation rights, not to create anything.
- conda (miniconda or anaconda) installed, for both Section 2
  (Postgres) and running the backend.
- Backend Python dependencies installed into a conda env named
  `Debate-Coach` (`pip install -r requirements.txt`). This doc
  doesn't cover creating that env from scratch.
- Node.js + npm installed, for the frontend.
- Your `GROQ_*` / `GEMINI_*` API keys already in `.env` — unrelated
  to anything below; see the key-naming convention documented in
  `.env.example` and `api/config.py` if you don't have these yet.

### 1. Backend — required `.env` values

A fresh `.env` needs more than what's filled into `.env.example` —
several values there are placeholders. Checked directly against
`app/core/config.py`'s `Settings` class:

Hard-required — `Settings()` raises at import time if any of these
three are missing, which surfaces as the app failing to start with a
`pydantic` `ValidationError`:
- `JWT_SECRET_KEY` — any random string for local dev, e.g.
  `python3 -c "import secrets; print(secrets.token_hex(32))"`.
  Doesn't need to match production.
- `GCP_PROJECT_ID` — `debate-coach-508804` (from `.env.example`; same
  project as production, just a different bucket — see Section 3).
- `GCP_STORAGE_BUCKET` — for local dev this should be the isolated
  dev bucket from Section 3
  (`GCP_STORAGE_BUCKET=debate-coach-508804-dev-recordings`), **not**
  the production bucket (`debate-coach-508804-recordings`).

Has a default in `Settings()` (so it won't crash on startup) but is
required in practice for local dev to do anything useful:
- `DATABASE_URL` — defaults to `""`; empty means every DB call fails.
  Point it at local Postgres from Section 2, not production Cloud
  SQL:
  `DATABASE_URL=postgresql+psycopg://coaching_app:<password>@127.0.0.1:5433/debate_coach_dev`
  (leave `CLOUD_SQL_CONNECTION_NAME` blank — it takes priority over
  `DATABASE_URL` when set, see `app/db/database.py`).

Optional, defaults to `false`:
- `VIDEO_ANALYSIS_ENABLED=true` — required to exercise the
  video-analysis feature at all. Confirmed still documented in root
  `.env.example` (added by commit `61f35b3`). With it absent or
  `false`, the signal-upload route 404s, session creation ignores
  `video_analysis`, and report responses omit every video field —
  the app behaves exactly as if the feature didn't exist. Must match
  the frontend's `NEXT_PUBLIC_VIDEO_ANALYSIS_ENABLED` (Section 4).

Not a `Settings()` field — an ambient variable the `google-auth`
library reads directly, not through `.env`:
- `GOOGLE_APPLICATION_CREDENTIALS` — must be **absent/unset** if
  you're using impersonated ADC login (Section 3) rather than a
  downloaded service-account key file. If it's set (even to a stale
  or wrong path) it takes priority over ADC and impersonation is
  silently ignored.
- `GCP_SERVICE_ACCOUNT_EMAIL` — leave **blank**. It's only consulted
  by `app/services/storage.py`'s `_resolve_signing_credentials()`
  when the ambient credentials can't sign a URL themselves
  (`hasattr(credentials, "sign_bytes")` is false) — true for Cloud
  Run's attached runtime service account in production, not true for
  either a downloaded key file or impersonated ADC, both of which
  can already self-sign.

Also required, but not an env var: **ffmpeg on PATH**
(`sudo apt install ffmpeg`, or `conda install -c conda-forge
ffmpeg`). Checked at startup (`app/main.py:34-38`) — if missing, the
app still starts and logs one `WARNING`-level line easy to scroll
past (`ffmpeg was not found on PATH. Every upload will fail at the
conversion step until it is installed.`); the actual failure doesn't
surface until someone uploads a recording, in
`app/services/audio_convert.py`.

### 2. Local Postgres (no sudo, no Docker required)

Verified working via conda:

```bash
conda create -y -n pgdev -c conda-forge postgresql=17
mkdir -p ~/.local/share/debate-coach-pg
conda run -n pgdev initdb -D ~/.local/share/debate-coach-pg -U postgres \
  --auth-local=trust --auth-host=scram-sha-256
conda run -n pgdev pg_ctl -D ~/.local/share/debate-coach-pg \
  -o "-p 5433 -k /tmp -c listen_addresses=127.0.0.1" \
  -l ~/.local/share/debate-coach-pg/server.log start
conda run -n pgdev psql -h /tmp -p 5433 -U postgres -d postgres \
  -c "CREATE ROLE coaching_app LOGIN PASSWORD '<choose-a-password>';"
conda run -n pgdev psql -h /tmp -p 5433 -U postgres -d postgres \
  -c "CREATE DATABASE debate_coach_dev OWNER coaching_app;"
```

Port `5433` (not `5432`) is deliberate, so this can never collide
with a system-wide Postgres install. The server binds to
`127.0.0.1` only.

To stop, then restart later (e.g. after a reboot):

```bash
conda run -n pgdev pg_ctl -D ~/.local/share/debate-coach-pg stop
conda run -n pgdev pg_ctl -D ~/.local/share/debate-coach-pg \
  -o "-p 5433 -k /tmp -c listen_addresses=127.0.0.1" \
  -l ~/.local/share/debate-coach-pg/server.log start
```

To tear down entirely: run the `stop` command above, then
`rm -rf ~/.local/share/debate-coach-pg` and
`conda env remove -n pgdev`.

No manual migration step needed: `Base.metadata.create_all()` runs
at every backend startup (`app/main.py:32`, inside the `lifespan`
hook) and creates any tables that don't exist yet against this empty
database. **Known tech debt** (already recorded in
`docs/video-analysis/README.md`, "Known tech debt: no real migration
mechanism"): `create_all()` only adds new tables, it never alters an
existing one, and Alembic is in `requirements.txt` with no
`alembic.ini`, no versions directory, and no deploy step wired up.
Fine for a from-empty local database; not a real migration story.

### 3. Isolated GCS dev bucket + credentials (never production storage)

Why: pointing local dev at the production bucket risks mixing test
uploads with real user recordings, and the default compute service
account holds broad `roles/storage.objectAdmin` across the whole
project.

Confirmed still true as of this writing:
- Key file creation is blocked by an org policy on this project —
  verify with
  `gcloud resource-manager org-policies describe constraints/iam.disableServiceAccountKeyCreation --project=debate-coach-508804 --effective`
  (should show `enforced: true`). Impersonated Application Default
  Credentials is the working alternative, not a downloaded key file.
- The dev bucket and service account **already exist** for this
  project (`gcloud storage buckets list` /
  `gcloud iam service-accounts list --project=debate-coach-508804`):
  bucket `debate-coach-508804-dev-recordings`, service account
  `debate-coach-dev@debate-coach-508804.iam.gserviceaccount.com`. If
  you're joining this existing project, **skip straight to the grant
  + login step below** — the creation commands are here for setting
  up a new project, not for you to re-run.

One-time setup (already done for this project; included for
reference / a new project):

```bash
gcloud storage buckets create gs://<project-id>-dev-recordings \
  --project=<project-id> --location=<region, match production> \
  --uniform-bucket-level-access

gcloud iam service-accounts create <name>-dev \
  --project=<project-id> --display-name="<App> local dev"

gcloud storage buckets add-iam-policy-binding gs://<project-id>-dev-recordings \
  --member="serviceAccount:<name>-dev@<project-id>.iam.gserviceaccount.com" \
  --role="roles/storage.objectAdmin"
```

What every new developer actually needs to run, against the
already-existing dev service account:

```bash
gcloud iam service-accounts add-iam-policy-binding \
  debate-coach-dev@debate-coach-508804.iam.gserviceaccount.com \
  --member="user:<your-gcloud-account-email>" \
  --role="roles/iam.serviceAccountTokenCreator"

gcloud auth application-default login \
  --impersonate-service-account=debate-coach-dev@debate-coach-508804.iam.gserviceaccount.com
```

Then in `.env`: `GCP_STORAGE_BUCKET=debate-coach-508804-dev-recordings`,
and leave `GOOGLE_APPLICATION_CREDENTIALS` unset entirely (see
Section 1).

**Critical caveat.** This ADC login is tied to this machine and this
`gcloud` user session — it is not portable via git or `.env`. It
must be redone (from the `gcloud auth application-default login
--impersonate-service-account=...` step) after: a machine reboot
that clears it, switching to a different machine, or running
`gcloud auth login` for a different account. If storage calls
suddenly fail with credential errors and nothing in `.env` changed,
this is the first thing to check. Verify which identity ADC
currently resolves to, from inside the backend conda env:

```bash
python3 -c "
import google.auth
creds, project = google.auth.default()
print(type(creds).__module__ + '.' + type(creds).__name__, getattr(creds, 'signer_email', None))
"
```

Should print `google.auth.impersonated_credentials.Credentials
debate-coach-dev@debate-coach-508804.iam.gserviceaccount.com` — not
a stale email, and not a crash.

### 4. Frontend — required `web/.env.local` values

At minimum:

```
NEXT_PUBLIC_API_URL=http://localhost:8000
NEXT_PUBLIC_STORAGE_ORIGIN=https://storage.googleapis.com
NEXT_PUBLIC_VIDEO_ANALYSIS_ENABLED=true
```

`NEXT_PUBLIC_STORAGE_ORIGIN` specifically: without it,
`web/next.config.mjs`'s Content-Security-Policy `connect-src` header
omits `storage.googleapis.com` entirely, and **every** recording
upload — audio-only included, with the video feature completely off
— silently fails in the browser console with a CSP violation,
surfacing to the user only as a generic "The recording could not be
sent" error. This predates the video-analysis feature: `git blame`
on `next.config.mjs` traces both the `storageOrigin` handling and
the `connect-src` line to commit `003d7134` ("Add web platform"),
the first commit on the `web-platform` branch this one forked from —
it is not something specific to video analysis, so don't file it
under a video-analysis-only heading if this doc gets reorganized.

**Critical caveat, happened twice in one session:** `web/.env.local`
can be silently reset to *only* a Vercel-CLI-generated
`VERCEL_OIDC_TOKEN`, wiping any manually-added lines, if something
invokes a `vercel` command against this project (`env pull`, `link`,
etc.) — even though the Vercel CLI isn't installed as a project
dependency here. After any such event, or if the app suddenly
behaves as though a flag or env var reverted, run
`cat web/.env.local` and re-add whatever's missing. Don't assume a
prior edit is still there — check.

Also: `NEXT_PUBLIC_*` values are compiled into the JS bundle when
`next dev` starts, not read live. A full kill-and-restart of the dev
server (not a hot reload, not saving a file) is required after any
change to `web/.env.local` or `web/.env` for it to take effect.

### 5. Startup order and verification

1. Start local Postgres (Section 2) if it isn't already running:
   `lsof -i :5433` to check.
2. Start the backend from the **repo root** (not from `web/`):
   `conda activate Debate-Coach && uvicorn app.main:app --reload --port 8000`
3. Watch the startup log before touching the frontend — it should
   get past loading Silero VAD with no `ValidationError` or
   traceback. If port 8000 is already in use from a previous run
   you forgot to kill, this is where `ERROR: [Errno 98] Address
   already in use` shows up; check with `lsof -i :8000` first.
4. Start the frontend: `cd web && npm run dev`.
5. Before touching the browser, confirm the CSP actually allows both
   destinations:
   ```bash
   curl -s -D - -o /dev/null http://localhost:3000/practice | grep -i content-security-policy
   ```
   Both `http://localhost:8000` and `storage.googleapis.com` should
   appear in the `connect-src` portion of the header.

## Notes

- **No service account key files.** Cloud Run authenticates as
  its attached service account automatically (Application
  Default Credentials via the metadata server) — this is how
  `app/services/storage.py` and `app/db/database.py` authenticate
  in production. `setup-gcp.sh` grants that account
  `roles/cloudsql.client`, `roles/storage.objectAdmin`, and
  `roles/iam.serviceAccountTokenCreator` on itself (needed to
  self-sign Cloud Storage URLs).
- **Local dev** needs its own credentials against its own isolated
  dev bucket, not the production one — see "Local development
  setup" above. A downloaded service-account key file is blocked by
  an org policy on this project; impersonated Application Default
  Credentials is the working path. Plain `gcloud auth
  application-default login` with no `--impersonate-service-account`
  authenticates as your own user account instead, which typically
  has far broader access than the app needs — don't use it for this.
- **Single Cloud Run instance concurrency caveat.** The backend
  keeps its LLM/Whisper API key pool and rate limiter in
  in-process memory (see the comment in `Dockerfile` and
  `app/main.py`). Cloud Run may run multiple container instances
  under load, each with its own independent view of that quota.
  If you see rate-limit errors that don't add up, check
  `gcloud run services describe debate-coach-backend --region us-central1`
  for instance count, and consider capping `--max-instances 1`
  until the key accounting is moved to shared storage.
- **`--allow-unauthenticated`** in `cloudbuild.yaml` makes the API
  publicly reachable, which the frontend needs. Auth is still
  enforced at the application layer (JWT), same as before.
