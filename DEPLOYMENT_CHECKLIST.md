# Deployment Checklist

- [x] `setup-gcp.sh` ran successfully
- [x] GCP resources created (bucket, Artifact Registry repo, Cloud SQL instance/db/user, IAM roles)
- [x] `.env.production` filled in (GCP values, `JWT_SECRET_KEY`, `DB_PASSWORD`, `GROQ_*`/`GEMINI_*` keys)
- [x] Backend deployed to Cloud Run: https://debate-coach-backend-7uc4kfztqq-uc.a.run.app
- [x] Backend health check passed (`{"status":"ok"}`)
- [ ] Vercel project connected
- [ ] Frontend deployed
- [ ] `ALLOWED_ORIGINS` updated with final Vercel domain and backend redeployed
- [ ] Full end-to-end test: record speech on the web app, confirm a report comes back

See `VERCEL_DEPLOYMENT.md` for the frontend steps.
