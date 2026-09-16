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
- [ ] web/ deployed to Vercel
- [ ] Environment variables set in Vercel
- [ ] Vercel domain assigned
- [ ] ALLOWED_ORIGINS updated on backend with Vercel domain

## Next steps
1. Deploy to Vercel using VERCEL_DEPLOYMENT.md
2. Get your Vercel domain
3. Run the ALLOWED_ORIGINS update command
4. Test end-to-end: sign up → record → analyze → view results

## Troubleshooting
- If backend crashes: check logs with `gcloud run services logs read debate-coach-backend --region us-central1 --limit 50`
- If frontend can't reach backend: verify NEXT_PUBLIC_API_URL matches the Cloud Run URL exactly
- If database connection fails: check DB_PASSWORD in .env.production is correct
