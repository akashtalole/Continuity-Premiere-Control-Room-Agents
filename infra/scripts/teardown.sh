#!/usr/bin/env bash
# Deletes the Cloud Run services created by deploy-all.sh, so a hackathon
# demo doesn't keep incurring charges after judging is over. Artifact
# Registry images and Secret Manager secrets are left in place (cheap to
# keep, and you may want to redeploy) -- delete them manually if you want a
# full teardown.
#
# Usage:
#   bash infra/scripts/teardown.sh                 # Cloud Run services only
#   bash infra/scripts/teardown.sh --with-cloudsql  # also deletes the Cloud SQL instance, if any

set -euo pipefail
cd "$(dirname "${BASH_SOURCE[0]}")"
source ./lib.sh

require_command gcloud
resolve_project_id

log "Deleting Cloud Run service '$FRONTEND_SERVICE'"
gcloud run services delete "$FRONTEND_SERVICE" --region "$REGION" --project "$PROJECT_ID" --quiet \
  || warn "Frontend service not found or already deleted."

log "Deleting Cloud Run service '$BACKEND_SERVICE'"
gcloud run services delete "$BACKEND_SERVICE" --region "$REGION" --project "$PROJECT_ID" --quiet \
  || warn "Backend service not found or already deleted."

if [[ "${1:-}" == "--with-cloudsql" ]]; then
  : "${INSTANCE_NAME:=premiere-control-room-db}"
  log "Deleting Cloud SQL instance '$INSTANCE_NAME'"
  gcloud sql instances delete "$INSTANCE_NAME" --project "$PROJECT_ID" --quiet \
    || warn "Cloud SQL instance not found or already deleted."
fi

rm -f ./.backend-url ./.frontend-url

log "Teardown complete."
