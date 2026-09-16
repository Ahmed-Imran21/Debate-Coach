# Deployment Checklist

- [x] `setup-gcp.sh` ran successfully
- [x] GCP resources created (bucket, Artifact Registry repo, Cloud SQL instance/db/user, IAM roles)
- [x] `.env.production` created from `.env.example`, GCP values and `JWT_SECRET_KEY` filled in
- [ ] `.env.production`: `DB_PASSWORD` filled in (still a placeholder — the password entered into `setup-gcp.sh` was masked input, never seen by Claude)
- [ ] `.env.production`: `GROQ_*` / `GEMINI_*` keys filled in (still placeholders)
- [ ] Backend deployed to Cloud Run
- [ ] Backend health check passed (`curl .../health` returns `{"status":"ok"}`)
- [ ] Vercel project connected
- [ ] Frontend deployed
- [ ] `ALLOWED_ORIGINS` updated with final Vercel domain and backend redeployed
- [ ] Full end-to-end test: record speech on the web app, confirm a report comes back

## Blocking right now

`.env.production` has two placeholder values that will make the backend fail
to start if deployed as-is:

- `DB_PASSWORD` — the password you typed into `setup-gcp.sh`'s prompt
- `GROQ_*_KEY_*` / `GEMINI_*_KEY_*` — your existing provider keys (missing
  keys won't crash the app, just leave it warning "No API keys were loaded"
  and unable to process any session)

Fill those into `.env.production`, then the deploy step (`gcloud builds
submit --config cloudbuild.yaml --substitutions=_ENV_VARS_FILE=.env.production`)
can run.
