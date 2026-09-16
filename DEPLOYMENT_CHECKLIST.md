# Deployment Checklist

- [x] `setup-gcp.sh` ran successfully
- [x] GCP resources created (bucket, Artifact Registry repo, Cloud SQL instance/db/user, IAM roles)
- [x] `.env.production` filled in (GCP values, `JWT_SECRET_KEY`, `DB_PASSWORD`, `GROQ_*`/`GEMINI_*` keys)
- [x] Backend deployed to Cloud Run: https://debate-coach-backend-7uc4kfztqq-uc.a.run.app
- [x] Backend health check passed (`{"status":"ok"}`)
- [x] Vercel project connected (`debate-coach1/web`, linked to GitHub)
- [x] Frontend deployed: https://web-debate-coach1.vercel.app
- [x] `ALLOWED_ORIGINS` updated with final Vercel domain and backend redeployed
- [ ] Full end-to-end test: record speech on the web app, confirm a report comes back

See `DEPLOYMENT_SUCCESS.md` for the full summary and troubleshooting notes.
