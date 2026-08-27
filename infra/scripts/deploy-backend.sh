#!/usr/bin/env bash
# Builds the backend image via Cloud Build and deploys it to Cloud Run,
# running as the dedicated backend service account created by 00-setup.sh
# (roles/aiplatform.user, secretmanager.secretAccessor, cloudsql.client,
# logging/monitoring writers -- see that script for exactly what it grants).
#
# Usage (from Google Cloud Shell, after infra/scripts/00-setup.sh):
#   bash infra/scripts/deploy-backend.sh
#
# Configuration is via environment variables (all optional -- sensible
# defaults run the real Gemini crew via Vertex AI against SQLite):
#   GRAFANA_URL                       Grafana Cloud stack URL
#   GRAFANA_SERVICE_ACCOUNT_TOKEN     stored in Secret Manager; prompted if unset and interactive
#   GOOGLE_API_KEY                    optional override: use the Gemini Developer API
#                                      instead of Vertex AI. Stored in Secret Manager;
#                                      prompted if unset and interactive.
#   GEMINI_MODEL                      default: gemini-flash-latest
#   DATABASE_URL                      default: SQLite (ephemeral -- see the warning this script prints)
#   CLOUDSQL_INSTANCE_CONNECTION_NAME set this (project:region:instance) to attach a Cloud SQL instance
#   OTEL_EXPORTER_OTLP_ENDPOINT       Grafana Cloud OTLP gateway, or leave unset for console-only telemetry
#   OTEL_EXPORTER_OTLP_HEADERS        stored in Secret Manager; e.g. "Authorization=Basic <base64>"
#   CORS_ORIGINS                      default: "*" (deploy-all.sh tightens this after the frontend deploys)
#
# Gemini auth defaults to Vertex AI: the backend authenticates as its own
# service account (no API key needed at all) via Application Default
# Credentials, using the roles/aiplatform.user role 00-setup.sh already
# granted it. Set GOOGLE_API_KEY to use the Gemini Developer API instead.
#
# Leaving GRAFANA_URL unset deploys the backend running the deterministic
# mock crew -- see docs/agents.md -- which is a legitimate, fully-functional
# way to get a live demo URL without Grafana credentials on hand yet.

set -euo pipefail
cd "$(dirname "${BASH_SOURCE[0]}")"
source ./lib.sh

require_command gcloud
resolve_project_id
ROOT="$(repo_root)"

: "${GEMINI_MODEL:=gemini-flash-latest}"
: "${GRAFANA_MCP_ENDPOINT:=https://mcp.grafana.com/mcp}"
: "${DATABASE_URL:=sqlite+aiosqlite:///./premiere_control_room.db}"
: "${DEMO_MODE:=true}"
: "${CORS_ORIGINS:=*}"

prompt_secret GOOGLE_API_KEY "Gemini API key -- leave blank to use Vertex AI via the service account instead (recommended)"
prompt_secret GRAFANA_SERVICE_ACCOUNT_TOKEN "Grafana service account token (leave blank if using hosted OAuth or the mock crew)"
prompt_secret OTEL_EXPORTER_OTLP_HEADERS "OTLP exporter headers, e.g. Authorization=Basic ... (leave blank for console-only telemetry)"

BACKEND_SA_EMAIL="$(service_account_email "$BACKEND_SA_NAME")"
if ! gcloud iam service-accounts describe "$BACKEND_SA_EMAIL" --project "$PROJECT_ID" >/dev/null 2>&1; then
  die "Service account $BACKEND_SA_EMAIL doesn't exist yet. Run infra/scripts/00-setup.sh first."
fi

IMAGE="$(image_uri backend)"
log "Building backend image: $IMAGE"
gcloud builds submit "$ROOT/backend" --tag "$IMAGE" --project "$PROJECT_ID"

# --- secrets -----------------------------------------------------------------

SET_SECRETS=()
put_secret_value premiere-control-room-google-api-key "${GOOGLE_API_KEY:-}"
[[ -n "${GOOGLE_API_KEY:-}" ]] && SET_SECRETS+=("GOOGLE_API_KEY=premiere-control-room-google-api-key:latest")

put_secret_value premiere-control-room-grafana-token "${GRAFANA_SERVICE_ACCOUNT_TOKEN:-}"
[[ -n "${GRAFANA_SERVICE_ACCOUNT_TOKEN:-}" ]] && SET_SECRETS+=("GRAFANA_SERVICE_ACCOUNT_TOKEN=premiere-control-room-grafana-token:latest")

put_secret_value premiere-control-room-otel-headers "${OTEL_EXPORTER_OTLP_HEADERS:-}"
[[ -n "${OTEL_EXPORTER_OTLP_HEADERS:-}" ]] && SET_SECRETS+=("OTEL_EXPORTER_OTLP_HEADERS=premiere-control-room-otel-headers:latest")

if [[ -n "${DATABASE_URL:-}" && "$DATABASE_URL" == postgresql* ]]; then
  put_secret_value premiere-control-room-database-url "$DATABASE_URL"
  SET_SECRETS+=("DATABASE_URL=premiere-control-room-database-url:latest")
  DATABASE_URL_ENV=""  # provided via secret instead
else
  DATABASE_URL_ENV="$DATABASE_URL"
fi

# --- Gemini auth mode ----------------------------------------------------------
# Default to Vertex AI (no key, uses the backend service account's ADC).
# An explicit GOOGLE_API_KEY switches to the Gemini Developer API instead,
# so the two modes are never both active at once.

if [[ -n "${GOOGLE_API_KEY:-}" ]]; then
  log "Gemini auth: Developer API key (GOOGLE_API_KEY secret)"
  USE_VERTEXAI=false
else
  log "Gemini auth: Vertex AI via service account $BACKEND_SA_EMAIL"
  USE_VERTEXAI=true
fi

# --- plain env vars ------------------------------------------------------------

ENV_VARS=(
  "GRAFANA_URL=${GRAFANA_URL:-}"
  "GRAFANA_MCP_ENDPOINT=${GRAFANA_MCP_ENDPOINT}"
  "GEMINI_MODEL=${GEMINI_MODEL}"
  "GOOGLE_CLOUD_PROJECT=${PROJECT_ID}"
  "GOOGLE_CLOUD_LOCATION=${REGION}"
  "GOOGLE_GENAI_USE_VERTEXAI=${USE_VERTEXAI}"
  "DEMO_MODE=${DEMO_MODE}"
  "CORS_ORIGINS=${CORS_ORIGINS}"
  "OTEL_EXPORTER_OTLP_ENDPOINT=${OTEL_EXPORTER_OTLP_ENDPOINT:-}"
)
[[ -n "$DATABASE_URL_ENV" ]] && ENV_VARS+=("DATABASE_URL=${DATABASE_URL_ENV}")

ENV_VARS_JOINED="$(IFS=,; echo "${ENV_VARS[*]}")"

DEPLOY_ARGS=(
  run deploy "$BACKEND_SERVICE"
  --image "$IMAGE"
  --region "$REGION"
  --project "$PROJECT_ID"
  --platform managed
  --service-account "$BACKEND_SA_EMAIL"
  --allow-unauthenticated
  --memory 512Mi
  --set-env-vars "$ENV_VARS_JOINED"
)

if [[ ${#SET_SECRETS[@]} -gt 0 ]]; then
  SECRETS_JOINED="$(IFS=,; echo "${SET_SECRETS[*]}")"
  DEPLOY_ARGS+=(--set-secrets "$SECRETS_JOINED")
fi

if [[ -n "${CLOUDSQL_INSTANCE_CONNECTION_NAME:-}" ]]; then
  DEPLOY_ARGS+=(--add-cloudsql-instances "$CLOUDSQL_INSTANCE_CONNECTION_NAME")
fi

if [[ "$DATABASE_URL" == sqlite* ]]; then
  warn "DATABASE_URL is SQLite -- each Cloud Run instance has its own ephemeral"
  warn "filesystem, and incident history will NOT persist across redeploys or"
  warn "cold starts after a long idle period. Pinning to a single instance"
  warn "(--min-instances=1 --max-instances=1) so at least concurrent requests"
  warn "see consistent data. For real persistence, provision Cloud SQL"
  warn "(infra/scripts/provision-cloudsql.sh) and re-run with DATABASE_URL set."
  DEPLOY_ARGS+=(--min-instances 1 --max-instances 1)
else
  DEPLOY_ARGS+=(--min-instances 0 --max-instances 10)
fi

log "Deploying $BACKEND_SERVICE to Cloud Run ($REGION) as $BACKEND_SA_EMAIL"
gcloud "${DEPLOY_ARGS[@]}"

BACKEND_URL="$(gcloud run services describe "$BACKEND_SERVICE" \
  --region "$REGION" --project "$PROJECT_ID" --format='value(status.url)')"

log "Backend deployed: $BACKEND_URL"
echo "$BACKEND_URL" > "$ROOT/infra/scripts/.backend-url"
