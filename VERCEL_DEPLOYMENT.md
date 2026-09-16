# Vercel Frontend Deployment

The backend is now running at: https://debate-coach-backend-7uc4kfztqq-uc.a.run.app

## Deploy web/ to Vercel

### Option A: Via Vercel CLI (fastest)
```bash
cd web
vercel --prod
```

### Option B: Via GitHub (recommended for long-term)
1. Push this repo to GitHub (if not already)
2. Go to vercel.com, click "New Project"
3. Import the GitHub repo
4. Set "Root Directory" to `web/`
5. Click "Deploy"

## Set environment variables in Vercel

In Vercel project settings → Environment Variables, add:

```
NEXT_PUBLIC_API_URL=https://debate-coach-backend-7uc4kfztqq-uc.a.run.app
NEXT_PUBLIC_STORAGE_ORIGIN=https://storage.googleapis.com
NEXT_PUBLIC_SITE_URL=https://debate-coach.vercel.app
```

`NEXT_PUBLIC_SITE_URL` is a placeholder — update it once Vercel assigns (or
you attach) the real domain, and redeploy the frontend so the build picks up
the change (`NEXT_PUBLIC_*` vars are baked in at build time, not read at
runtime).

## After deployment: update ALLOWED_ORIGINS

Vercel will give you a real domain, e.g. `https://debate-coach-abc123.vercel.app`
(or your custom domain, if you attach one). Update it in two places:

1. **Vercel project settings → Domains** — attach your real domain if you have one.
2. **Backend `ALLOWED_ORIGINS`**, so CORS accepts requests from the real domain:
   ```bash
   gcloud run services update debate-coach-backend \
     --region us-central1 \
     --update-env-vars ALLOWED_ORIGINS="http://localhost:3000,https://[YOUR-VERCEL-DOMAIN]"
   ```
   Also update `ALLOWED_ORIGINS` in `.env.production` locally so it stays in
   sync for the next full redeploy via `cloudbuild.yaml` (a plain `--update-env-vars`
   patches the live service but doesn't touch that file).

## Test end-to-end

1. Go to your Vercel domain
2. Sign up with a test account
3. Record a short speech (10-30 seconds)
4. Wait for analysis (2-5 minutes)
5. See results

If a session gets stuck or errors out, check backend logs:
```bash
gcloud run services logs read debate-coach-backend --region us-central1 --limit 50
```
