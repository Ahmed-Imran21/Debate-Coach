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

## Notes

- **No service account key files.** Cloud Run authenticates as
  its attached service account automatically (Application
  Default Credentials via the metadata server) — this is how
  `app/services/storage.py` and `app/db/database.py` authenticate
  in production. `setup-gcp.sh` grants that account
  `roles/cloudsql.client`, `roles/storage.objectAdmin`, and
  `roles/iam.serviceAccountTokenCreator` on itself (needed to
  self-sign Cloud Storage URLs).
- **Local dev** needs its own credentials:
  `gcloud auth application-default login`, or point
  `GOOGLE_APPLICATION_CREDENTIALS` at a downloaded service-account
  key file. Either way, that identity needs read/write access to
  the bucket and (for local Postgres) doesn't need Cloud SQL roles
  at all if you're running Postgres locally instead.
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
