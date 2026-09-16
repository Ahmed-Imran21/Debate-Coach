#!/usr/bin/env bash
#
# Sets NEXT_PUBLIC_API_URL, NEXT_PUBLIC_STORAGE_ORIGIN, and
# NEXT_PUBLIC_SITE_URL as Vercel production environment variables
# for web/, then redeploys with `vercel --prod` so the build
# picks them up (NEXT_PUBLIC_* vars are baked in at build time,
# not read at runtime, so a plain env var change alone wouldn't
# reach the live site without a rebuild).
#
# Run from the repo root:
#   ./setup-vercel-env.sh
#
# Requires being logged in (`vercel login`) and, on first run,
# will prompt to link web/ to a Vercel project if it isn't
# already linked.

set -euo pipefail

vercel_cmd() {
  if command -v vercel >/dev/null 2>&1; then
    vercel "$@"
  else
    npx --yes vercel "$@"
  fi
}

REGION="us-central1"
SERVICE_NAME="debate-coach-backend"

echo "--- Cloud Run URL ---"
API_URL="$(gcloud run services describe "${SERVICE_NAME}" --region "${REGION}" --format='value(status.url)' 2>/dev/null || true)"

if [ -z "${API_URL}" ]; then
  echo "Could not fetch it automatically (gcloud not configured, or the service isn't deployed yet)."
  read -rp "Paste the Cloud Run backend URL: " API_URL
fi

if [ -z "${API_URL}" ]; then
  echo "No URL provided, aborting." >&2
  exit 1
fi

echo "Using API URL: ${API_URL}"

STORAGE_ORIGIN="https://storage.googleapis.com"
SITE_URL="https://debate-coach.vercel.app"

echo
echo "--- Setting Vercel environment variables (production) ---"

set_env() {
  local name="$1"
  local value="$2"

  # Idempotent: drop any existing value for this name/environment
  # first, since `vercel env add` errors out if one is already set.
  vercel_cmd env rm "${name}" production --yes >/dev/null 2>&1 || true

  printf '%s' "${value}" | vercel_cmd env add "${name}" production
}

(
  cd web
  set_env NEXT_PUBLIC_API_URL "${API_URL}"
  set_env NEXT_PUBLIC_STORAGE_ORIGIN "${STORAGE_ORIGIN}"
  set_env NEXT_PUBLIC_SITE_URL "${SITE_URL}"
)

echo
echo "--- Redeploying to production ---"
(cd web && vercel_cmd --prod)

echo
echo "=== Done ==="
echo "Set on Vercel (production):"
echo "  NEXT_PUBLIC_API_URL         = ${API_URL}"
echo "  NEXT_PUBLIC_STORAGE_ORIGIN  = ${STORAGE_ORIGIN}"
echo "  NEXT_PUBLIC_SITE_URL        = ${SITE_URL}"
echo
echo "NEXT_PUBLIC_SITE_URL is still a placeholder. Once Vercel assigns"
echo "(or you attach) the real domain, update it and redeploy, then update"
echo "ALLOWED_ORIGINS on the backend to match (see VERCEL_DEPLOYMENT.md)."
