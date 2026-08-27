#!/usr/bin/env bash
# One-time (idempotent) project setup: enables the required GCP APIs and
# creates the Artifact Registry repo the other scripts push images to.
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
  --project "$PROJECT_ID"

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

log "Setup complete. Next: bash infra/scripts/deploy-all.sh"
