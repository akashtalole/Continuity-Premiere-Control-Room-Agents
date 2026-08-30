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
#   GRAFANA_SERVICE_ACCOUNT_TOKEN     stored in Secret Manager; prompted if unset and interactive.
#                                      Used both for the dashboard panel-image render API and,
#                                      if self-hosting mcp-grafana, as its own credential.
#   GRAFANA_MCP_ENDPOINT              defaults to the self-hosted mcp-grafana URL written by
#                                      deploy-mcp-grafana.sh (if it was run), else the hosted
#                                      mcp.grafana.com endpoint -- see that script's header
#                                      comment for why hosted alone won't work here.
#   GOOGLE_API_KEY                    optional override: use the Gemini Developer API
#                                      instead of Vertex AI. Stored in Secret Manager;
#                                      prompted if unset and interactive.
#   GEMINI_MODEL                      default: gemini-flash-latest
#   DATABASE_URL                      default: SQLite, for users/audit-log/workspaces only (see the warning this script prints)
#   CLOUDSQL_INSTANCE_CONNECTION_NAME set this (project:region:instance) to attach a Cloud SQL instance
#   FIRESTORE_PROJECT_ID              default: same project as GOOGLE_CLOUD_PROJECT. Incidents/agent events/
#                                      postmortems/token usage live here (see infra/scripts/00-setup.sh,
#                                      which provisions the Firestore database and grants roles/datastore.user).
#                                      Override only if Firestore lives in a different project.
#   OTEL_EXPORTER_OTLP_ENDPOINT       Grafana Cloud OTLP gateway, or leave unset for console-only telemetry
#   OTEL_EXPORTER_OTLP_HEADERS        stored in Secret Manager; e.g. "Authorization=Basic <base64>"
#   CORS_ORIGINS                      default: "*" (deploy-all.sh tightens this after the frontend deploys)
#   ADMIN_EMAIL / ADMIN_PASSWORD      bootstrap admin account, created once on first boot against an empty
#                                      users table (a later change here has no effect once that account
#                                      already exists -- see the warning this script prints). ADMIN_PASSWORD
#                                      is stored in Secret Manager. Leaving both unset generates a random
#                                      password for admin@premiere.local, logged once on first boot
#                                      (`gcloud run services logs read`).
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
: "${DATABASE_URL:=sqlite+aiosqlite:///./premiere_control_room.db}"
: "${DEMO_MODE:=true}"
: "${CORS_ORIGINS:=*}"

if [[ -z "${GRAFANA_MCP_ENDPOINT:-}" ]]; then
  if [[ -f "$ROOT/infra/scripts/.mcp-grafana-url" ]]; then
    GRAFANA_MCP_ENDPOINT="$(cat "$ROOT/infra/scripts/.mcp-grafana-url")"
    log "Using self-hosted mcp-grafana endpoint from deploy-mcp-grafana.sh: $GRAFANA_MCP_ENDPOINT"
  else
    GRAFANA_MCP_ENDPOINT="https://mcp.grafana.com/mcp"
  fi
fi

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

put_secret_value premiere-control-room-admin-password "${ADMIN_PASSWORD:-}"
[[ -n "${ADMIN_PASSWORD:-}" ]] && SET_SECRETS+=("ADMIN_PASSWORD=premiere-control-room-admin-password:latest")

# Only present once deploy-mcp-grafana.sh has been run -- the caller-auth
# token this backend presents to the self-hosted MCP server (see mcp.py).
# Not relevant, and not set, when using the hosted mcp.grafana.com endpoint.
if gcloud secrets describe premiere-control-room-mcp-server-token --project "$PROJECT_ID" >/dev/null 2>&1; then
  SET_SECRETS+=("GRAFANA_MCP_SERVER_TOKEN=premiere-control-room-mcp-server-token:latest")
  log "Found a self-hosted mcp-grafana caller-auth token; wiring it into the backend"
fi

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
[[ -n "${FIRESTORE_PROJECT_ID:-}" ]] && ENV_VARS+=("FIRESTORE_PROJECT_ID=${FIRESTORE_PROJECT_ID}")
[[ -n "${ADMIN_EMAIL:-}" ]] && ENV_VARS+=("ADMIN_EMAIL=${ADMIN_EMAIL}")

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
  warn "filesystem, so users/audit-log/workspaces will NOT persist across"
  warn "redeploys or cold starts after a long idle period. (Incidents/agent"
  warn "events/postmortems/token usage are unaffected -- those live in"
  warn "Firestore, not SQLite; see infra/scripts/00-setup.sh.) Pinning to a"
  warn "single instance (--min-instances=1 --max-instances=1) so at least"
  warn "concurrent requests see consistent user/audit data. For real"
  warn "persistence, provision Cloud SQL (infra/scripts/provision-cloudsql.sh)"
  warn "and re-run with DATABASE_URL set."
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

if [[ -n "${ADMIN_EMAIL:-}" || -n "${ADMIN_PASSWORD:-}" ]]; then
  warn "ADMIN_EMAIL/ADMIN_PASSWORD only take effect against an EMPTY users"
  warn "table -- the bootstrap admin is created once, on the first boot that"
  warn "finds no users at all, and never updated after. If this service has"
  warn "booted before (with different/no admin vars, e.g. a prior random"
  warn "password), this deploy did NOT change that account -- log in with the"
  warn "original credentials instead (check this revision's logs for the"
  warn "'No ADMIN_PASSWORD set' line: gcloud run services logs read"
  warn "$BACKEND_SERVICE --region $REGION), then use POST /api/auth/users to"
  warn "create the account you actually want. To force a fresh bootstrap"
  warn "instead: on SQLite, that means a container that has never booted --"
  warn "not guaranteed by a redeploy alone if min-instances kept an old one"
  warn "warm; on Cloud SQL/Postgres, delete the existing row from the users table."
fi
