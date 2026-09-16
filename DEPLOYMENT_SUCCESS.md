# Deployment Success ✓

## Backend (Cloud Run)
- [x] setup-gcp.sh completed
- [x] Cloud SQL database created
- [x] Cloud Storage bucket created
- [x] .env.production filled in
- [x] gcloud builds submit completed
- [x] Health check passed
- **Backend URL:** https://debate-coach-backend-7uc4kfztqq-uc.a.run.app

## Frontend (Vercel)
- [x] web/ deployed to Vercel (project `debate-coach1/web`)
- [x] Environment variables set in Vercel (production)
- [x] Vercel domain assigned
- [x] ALLOWED_ORIGINS updated on backend with Vercel domain
- **Frontend URL:** https://web-debate-coach1.vercel.app
  (also aliased at https://web-psi-snowy-10nijb344i.vercel.app)

## Next steps
1. Test end-to-end: sign up → record → analyze → view results
2. If you attach a custom domain in Vercel later, add it to `ALLOWED_ORIGINS`
   on the backend (`.env.production` + `gcloud run services update`) and to
   `NEXT_PUBLIC_SITE_URL` on Vercel, then redeploy both

## Troubleshooting
- If backend crashes: check logs with `gcloud run services logs read debate-coach-backend --region us-central1 --limit 50`
- If frontend can't reach backend: verify NEXT_PUBLIC_API_URL matches the Cloud Run URL exactly
- If database connection fails: check DB_PASSWORD in .env.production is correct
- If CORS errors appear in the browser console: confirm the exact frontend origin is in the backend's ALLOWED_ORIGINS
