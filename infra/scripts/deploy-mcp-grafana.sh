#!/usr/bin/env bash
# Deploys the open-source `grafana/mcp-grafana` server to Cloud Run, so the
# backend's ADK agent crew has a real, headless-usable Grafana Cloud MCP
# endpoint to call.
#
# This exists because Grafana's *hosted* MCP server (https://mcp.grafana.com/mcp)
# only supports an interactive, browser-based OAuth 2.1 login -- there is no
# service-account option, so it cannot be driven from an unattended Cloud Run
# backend. The self-hosted server is the documented alternative for exactly
# this case (see docs/agents.md#grafana-mcp-tool-access).
#
# Usage (from Google Cloud Shell, after infra/scripts/00-setup.sh):
#   export GRAFANA_URL="https://<stack>.grafana.net"
#   export GRAFANA_SERVICE_ACCOUNT_TOKEN="<service account token, Editor role or higher>"
#   bash infra/scripts/deploy-mcp-grafana.sh
#
# GRAFANA_SERVICE_ACCOUNT_TOKEN is this server's own credential for calling
# your Grafana stack -- create it under your stack's Administration > Service
# accounts. It's stored in Secret Manager, never left as a plain env var.
#
# MCP_GRAFANA_SERVER_TOKEN is a *different* secret: the one callers (this
# project's backend) must present to reach this server at all, since it's
# deployed publicly reachable on Cloud Run. Generated automatically if you
# don't set one; deploy-backend.sh reads the same generated value back out of
# Secret Manager, so you don't need to copy it around by hand.

set -euo pipefail
cd "$(dirname "${BASH_SOURCE[0]}")"
source ./lib.sh

require_command gcloud
resolve_project_id
ROOT="$(repo_root)"

[[ -n "${GRAFANA_URL:-}" ]] || die "GRAFANA_URL is required, e.g. https://<stack>.grafana.net"
prompt_secret GRAFANA_SERVICE_ACCOUNT_TOKEN "Grafana service account token (Editor role or higher)"
[[ -n "${GRAFANA_SERVICE_ACCOUNT_TOKEN:-}" ]] || die "GRAFANA_SERVICE_ACCOUNT_TOKEN is required to self-host mcp-grafana."

MCP_GRAFANA_SA_EMAIL="$(service_account_email "$MCP_GRAFANA_SA_NAME")"
if ! gcloud iam service-accounts describe "$MCP_GRAFANA_SA_EMAIL" --project "$PROJECT_ID" >/dev/null 2>&1; then
  die "Service account $MCP_GRAFANA_SA_EMAIL doesn't exist yet. Run infra/scripts/00-setup.sh first."
fi

: "${MCP_GRAFANA_IMAGE:=docker.io/grafana/mcp-grafana:latest}"

# Generate a caller-auth token if one wasn't provided, and reuse whatever's
# already stored so re-running this script doesn't rotate it out from under
# a backend that's already deployed against the old value.
if [[ -z "${MCP_GRAFANA_SERVER_TOKEN:-}" ]]; then
  if gcloud secrets versions access latest --secret=premiere-control-room-mcp-server-token --project "$PROJECT_ID" >/dev/null 2>&1; then
    MCP_GRAFANA_SERVER_TOKEN="$(gcloud secrets versions access latest --secret=premiere-control-room-mcp-server-token --project "$PROJECT_ID")"
    log "Reusing existing MCP_GRAFANA_SERVER_TOKEN from Secret Manager"
  else
    MCP_GRAFANA_SERVER_TOKEN="$(random_token)"
    log "Generated a new MCP_GRAFANA_SERVER_TOKEN"
  fi
fi

# Same secret name deploy-backend.sh uses for GRAFANA_SERVICE_ACCOUNT_TOKEN --
# it's the same credential (this backend also calls Grafana's render API
# directly for dashboard panel images), shared rather than duplicated so
# there's one token to rotate, not two copies that can drift.
put_secret_value premiere-control-room-grafana-token "$GRAFANA_SERVICE_ACCOUNT_TOKEN"
put_secret_value premiere-control-room-mcp-server-token "$MCP_GRAFANA_SERVER_TOKEN"

log "Deploying $MCP_GRAFANA_SERVICE to Cloud Run ($REGION) as $MCP_GRAFANA_SA_EMAIL"
gcloud run deploy "$MCP_GRAFANA_SERVICE" \
  --image "$MCP_GRAFANA_IMAGE" \
  --region "$REGION" \
  --project "$PROJECT_ID" \
  --platform managed \
  --service-account "$MCP_GRAFANA_SA_EMAIL" \
  --allow-unauthenticated \
  --port 8080 \
  --memory 256Mi \
  --min-instances 0 \
  --max-instances 3 \
  --args="-t,streamable-http,--address,0.0.0.0:8080" \
  --set-env-vars "GRAFANA_URL=${GRAFANA_URL}" \
  --set-secrets "GRAFANA_SERVICE_ACCOUNT_TOKEN=premiere-control-room-grafana-token:latest,MCP_GRAFANA_SERVER_TOKEN=premiere-control-room-mcp-server-token:latest"

MCP_GRAFANA_URL="$(gcloud run services describe "$MCP_GRAFANA_SERVICE" \
  --region "$REGION" --project "$PROJECT_ID" --format='value(status.url)')"

log "mcp-grafana deployed: $MCP_GRAFANA_URL"
warn "It's reachable by anyone (--allow-unauthenticated), gated only by the"
warn "MCP_GRAFANA_SERVER_TOKEN caller-auth secret -- keep that secret private."

echo "${MCP_GRAFANA_URL}/mcp" > "$ROOT/infra/scripts/.mcp-grafana-url"
echo "$MCP_GRAFANA_SERVER_TOKEN" > "$ROOT/infra/scripts/.mcp-grafana-server-token"
chmod 600 "$ROOT/infra/scripts/.mcp-grafana-server-token"
