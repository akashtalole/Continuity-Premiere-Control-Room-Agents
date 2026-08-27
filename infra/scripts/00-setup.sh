#!/usr/bin/env bash
# One-time (idempotent) project setup: enables the required GCP APIs, fixes
# a common Cloud Build permission gap, creates the Artifact Registry repo,
# and creates the dedicated service accounts the backend and frontend
# Cloud Run services run as -- including Vertex AI access for the backend
# so the agent crew can call Gemini using the service account's
# Application Default Credentials, with no API key required.
#
# Usage (from Google Cloud Shell, with a project already selected):
#   bash infra/scripts/00-setup.sh
#
# Override the region with: REGION=europe-west1 bash infra/scripts/00-setup.sh

set -euo pipefail
cd "$(dirname "${BASH_SOURCE[0]}")"
source ./lib.sh

require_command gcloud
resolve_project_id

log "Project:  $PROJECT_ID"
log "Region:   $REGION"

log "Enabling required APIs (safe to re-run; already-enabled APIs are skipped)"
gcloud services enable \
  run.googleapis.com \
  cloudbuild.googleapis.com \
  artifactregistry.googleapis.com \
  secretmanager.googleapis.com \
  aiplatform.googleapis.com \
  iam.googleapis.com \
  compute.googleapis.com \
  --project "$PROJECT_ID"

# Newer projects don't automatically grant Cloud Build's default runtime
# identity (the Compute Engine default service account) read access to the
# GCS bucket Cloud Build uploads your source to, which fails every
# `gcloud builds submit` with a "storage.objects.get" 403 before a single
# build step runs. This is the documented fix.
log "Granting Cloud Build's default service account source-bucket access"
grant_project_role \
  "serviceAccount:$(project_number)-compute@developer.gserviceaccount.com" \
  "roles/cloudbuild.builds.builder"

if gcloud artifacts repositories describe "$REPO_NAME" \
    --location "$REGION" --project "$PROJECT_ID" >/dev/null 2>&1; then
  log "Artifact Registry repo '$REPO_NAME' already exists in $REGION"
else
  log "Creating Artifact Registry repo '$REPO_NAME' in $REGION"
  gcloud artifacts repositories create "$REPO_NAME" \
    --repository-format=docker \
    --location "$REGION" \
    --project "$PROJECT_ID" \
    --description="Premiere Control Room backend + frontend images"
fi

log "Configuring Docker auth for $(artifact_registry_host)"
gcloud auth configure-docker "$(artifact_registry_host)" --quiet --project "$PROJECT_ID" >/dev/null

# --- dedicated service accounts ----------------------------------------------
# Cloud Run services default to the broad, shared Compute Engine default
# service account if none is specified. Each service gets its own
# least-privilege identity instead.

ensure_service_account "$BACKEND_SA_NAME" "Premiere Control Room backend (Cloud Run)"
BACKEND_SA_EMAIL="$(service_account_email "$BACKEND_SA_NAME")"

log "Granting backend service account ($BACKEND_SA_EMAIL) its runtime roles"
grant_project_role "serviceAccount:$BACKEND_SA_EMAIL" "roles/aiplatform.user"          # Gemini via Vertex AI
grant_project_role "serviceAccount:$BACKEND_SA_EMAIL" "roles/secretmanager.secretAccessor"  # Grafana/OTLP secrets
grant_project_role "serviceAccount:$BACKEND_SA_EMAIL" "roles/cloudsql.client"          # no-op unless Cloud SQL is attached
grant_project_role "serviceAccount:$BACKEND_SA_EMAIL" "roles/logging.logWriter"
grant_project_role "serviceAccount:$BACKEND_SA_EMAIL" "roles/monitoring.metricWriter"

ensure_service_account "$FRONTEND_SA_NAME" "Premiere Control Room frontend (Cloud Run)"
FRONTEND_SA_EMAIL="$(service_account_email "$FRONTEND_SA_NAME")"

log "Granting frontend service account ($FRONTEND_SA_EMAIL) its runtime roles"
grant_project_role "serviceAccount:$FRONTEND_SA_EMAIL" "roles/logging.logWriter"
grant_project_role "serviceAccount:$FRONTEND_SA_EMAIL" "roles/monitoring.metricWriter"

log "Setup complete."
log "  Backend service account:  $BACKEND_SA_EMAIL"
log "  Frontend service account: $FRONTEND_SA_EMAIL"
log "Next: bash infra/scripts/deploy-all.sh"
