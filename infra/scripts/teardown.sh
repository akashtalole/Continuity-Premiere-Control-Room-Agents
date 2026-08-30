#!/usr/bin/env bash
# Deletes the Cloud Run services created by deploy-all.sh, so a hackathon
# demo doesn't keep incurring charges after judging is over. Artifact
# Registry images, Secret Manager secrets, the Firestore database (incident
# data), and the enabled APIs are left in place (cheap/free to keep, and you
# may want to redeploy) -- delete them manually if you want a full teardown.
# (Firestore in particular: a project gets exactly one database, and it
# can't be recreated for a cooldown period after deletion, so this script
# never touches it.)
#
# Usage:
#   bash infra/scripts/teardown.sh                        # Cloud Run services only
#   bash infra/scripts/teardown.sh --with-cloudsql         # also deletes the Cloud SQL instance, if any
#   bash infra/scripts/teardown.sh --with-service-accounts # also deletes the backend/frontend service accounts
#
# Flags can be combined: --with-cloudsql --with-service-accounts

set -euo pipefail
cd "$(dirname "${BASH_SOURCE[0]}")"
source ./lib.sh

require_command gcloud
resolve_project_id

WITH_CLOUDSQL=false
WITH_SERVICE_ACCOUNTS=false
for arg in "$@"; do
  case "$arg" in
    --with-cloudsql) WITH_CLOUDSQL=true ;;
    --with-service-accounts) WITH_SERVICE_ACCOUNTS=true ;;
    *) die "Unknown flag: $arg" ;;
  esac
done

log "Deleting Cloud Run service '$FRONTEND_SERVICE'"
gcloud run services delete "$FRONTEND_SERVICE" --region "$REGION" --project "$PROJECT_ID" --quiet \
  || warn "Frontend service not found or already deleted."

log "Deleting Cloud Run service '$BACKEND_SERVICE'"
gcloud run services delete "$BACKEND_SERVICE" --region "$REGION" --project "$PROJECT_ID" --quiet \
  || warn "Backend service not found or already deleted."

log "Deleting Cloud Run service '$MCP_GRAFANA_SERVICE'"
gcloud run services delete "$MCP_GRAFANA_SERVICE" --region "$REGION" --project "$PROJECT_ID" --quiet \
  || warn "mcp-grafana service not found or already deleted (fine if you're on the mock crew)."

if [[ "$WITH_CLOUDSQL" == true ]]; then
  : "${INSTANCE_NAME:=premiere-control-room-db}"
  log "Deleting Cloud SQL instance '$INSTANCE_NAME'"
  gcloud sql instances delete "$INSTANCE_NAME" --project "$PROJECT_ID" --quiet \
    || warn "Cloud SQL instance not found or already deleted."
fi

if [[ "$WITH_SERVICE_ACCOUNTS" == true ]]; then
  for sa_name in "$BACKEND_SA_NAME" "$FRONTEND_SA_NAME" "$MCP_GRAFANA_SA_NAME"; do
    email="$(service_account_email "$sa_name")"
    log "Deleting service account '$email'"
    gcloud iam service-accounts delete "$email" --project "$PROJECT_ID" --quiet \
      || warn "Service account $email not found or already deleted."
  done
fi

rm -f ./.backend-url ./.frontend-url ./.mcp-grafana-url ./.mcp-grafana-server-token

log "Teardown complete."
