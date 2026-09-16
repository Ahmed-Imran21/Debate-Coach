#!/usr/bin/env bash
#
# One-time GCP resource setup for Debate Coach: enables the
# required APIs, creates the Cloud Storage bucket, the Cloud SQL
# instance/database/user, an Artifact Registry repository for
# the backend image, and grants the IAM roles the Cloud Run
# service account needs at runtime.
#
# Run once per environment, from the repo root:
#   ./setup-gcp.sh
#
# Idempotent: safe to re-run if a step fails partway through.

set -euo pipefail

PROJECT_ID="debate-coach-508804"
REGION="us-central1"

BUCKET_NAME="debate-coach-508804-recordings"

SQL_INSTANCE="debate-coach-db"
SQL_TIER="db-custom-1-3840"
DB_NAME="debate_coach"
DB_USER="coaching_app"

ARTIFACT_REPO="debate-coach"

RUN_SERVICE_NAME="debate-coach-backend"

echo "=== Debate Coach GCP setup ==="
echo "Project: ${PROJECT_ID}"
echo "Region:  ${REGION}"
echo

gcloud config set project "${PROJECT_ID}"

echo "--- Enabling required APIs ---"
gcloud services enable \
  run.googleapis.com \
  sqladmin.googleapis.com \
  storage.googleapis.com \
  artifactregistry.googleapis.com \
  cloudbuild.googleapis.com \
  iamcredentials.googleapis.com

echo "--- Creating Cloud Storage bucket ---"
if gcloud storage buckets describe "gs://${BUCKET_NAME}" >/dev/null 2>&1; then
  echo "Bucket gs://${BUCKET_NAME} already exists, skipping."
else
  gcloud storage buckets create "gs://${BUCKET_NAME}" \
    --location="${REGION}" \
    --uniform-bucket-level-access
fi

echo "--- Creating Artifact Registry repository ---"
if gcloud artifacts repositories describe "${ARTIFACT_REPO}" --location="${REGION}" >/dev/null 2>&1; then
  echo "Repository ${ARTIFACT_REPO} already exists, skipping."
else
  gcloud artifacts repositories create "${ARTIFACT_REPO}" \
    --repository-format=docker \
    --location="${REGION}" \
    --description="Debate Coach backend images"
fi

echo "--- Creating Cloud SQL instance (this can take 5-10 minutes) ---"
if gcloud sql instances describe "${SQL_INSTANCE}" >/dev/null 2>&1; then
  echo "Instance ${SQL_INSTANCE} already exists, skipping."
else
  gcloud sql instances create "${SQL_INSTANCE}" \
    --database-version=POSTGRES_15 \
    --tier="${SQL_TIER}" \
    --region="${REGION}" \
    --storage-auto-increase
fi

echo "--- Creating database ---"
if gcloud sql databases describe "${DB_NAME}" --instance="${SQL_INSTANCE}" >/dev/null 2>&1; then
  echo "Database ${DB_NAME} already exists, skipping."
else
  gcloud sql databases create "${DB_NAME}" --instance="${SQL_INSTANCE}"
fi

echo "--- Creating database user ---"
echo "Enter a password for the '${DB_USER}' database user:"
read -rs DB_PASSWORD
echo

if gcloud sql users list --instance="${SQL_INSTANCE}" --format="value(name)" | grep -qx "${DB_USER}"; then
  echo "User ${DB_USER} already exists, updating password."
  gcloud sql users set-password "${DB_USER}" \
    --instance="${SQL_INSTANCE}" \
    --password="${DB_PASSWORD}"
else
  gcloud sql users create "${DB_USER}" \
    --instance="${SQL_INSTANCE}" \
    --password="${DB_PASSWORD}"
fi

CLOUD_SQL_CONNECTION_NAME="${PROJECT_ID}:${REGION}:${SQL_INSTANCE}"

echo "--- Granting IAM roles to the default Compute service account ---"
# Cloud Run uses this account at runtime unless you attach a
# different one with --service-account. It needs:
#   - roles/cloudsql.client       to reach the Cloud SQL instance
#   - roles/storage.objectAdmin   to read/write the recordings bucket
#   - roles/iam.serviceAccountTokenCreator on itself, so the
#     backend can self-sign Cloud Storage URLs (see
#     app/services/storage.py) without a downloaded key file.
PROJECT_NUMBER=$(gcloud projects describe "${PROJECT_ID}" --format="value(projectNumber)")
RUN_SA="${PROJECT_NUMBER}-compute@developer.gserviceaccount.com"

gcloud projects add-iam-policy-binding "${PROJECT_ID}" \
  --member="serviceAccount:${RUN_SA}" \
  --role="roles/cloudsql.client" \
  --condition=None

gcloud storage buckets add-iam-policy-binding "gs://${BUCKET_NAME}" \
  --member="serviceAccount:${RUN_SA}" \
  --role="roles/storage.objectAdmin"

gcloud iam service-accounts add-iam-policy-binding "${RUN_SA}" \
  --member="serviceAccount:${RUN_SA}" \
  --role="roles/iam.serviceAccountTokenCreator" \
  --condition=None

echo
echo "=== Done ==="
echo
echo "Add these to your .env / .env.production:"
echo
echo "GCP_PROJECT_ID=${PROJECT_ID}"
echo "GCP_STORAGE_BUCKET=${BUCKET_NAME}"
echo "GCP_SERVICE_ACCOUNT_EMAIL=${RUN_SA}"
echo "CLOUD_SQL_CONNECTION_NAME=${CLOUD_SQL_CONNECTION_NAME}"
echo "DB_USER=${DB_USER}"
echo "DB_PASSWORD=<the password you just entered>"
echo "DB_NAME=${DB_NAME}"
echo
echo "Cloud SQL connection name (also needed by cloudbuild.yaml's"
echo "_CLOUD_SQL_INSTANCE substitution): ${CLOUD_SQL_CONNECTION_NAME}"
