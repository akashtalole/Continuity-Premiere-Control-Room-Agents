#!/usr/bin/env bash
# End-to-end deploy from a clean Google Cloud Shell: enables APIs, builds
# and deploys both services, then tightens the backend's CORS policy down
# to the frontend's real URL (it starts permissive since the frontend's URL
# isn't known until after it's deployed -- see deploy-backend.sh).
#
# Usage:
#   git clone <this repo> && cd Agentic-Cinema-The-Blockbuster-Hackathon
#   gcloud config set project <PROJECT_ID>
#   bash infra/scripts/deploy-all.sh
#
# See deploy-backend.sh's header comment for the environment variables that
# configure Grafana credentials, Cloud SQL, and OTLP export -- export them
# before running this script, or just run it with none set to get a live
# demo URL on the deterministic mock crew (Gemini access via Vertex AI and
# the dedicated service accounts this creates are wired up either way).

set -euo pipefail
cd "$(dirname "${BASH_SOURCE[0]}")"
source ./lib.sh

log "Step 1/4: project setup"
bash ./00-setup.sh

log "Step 2/4: deploy backend"
bash ./deploy-backend.sh
BACKEND_URL="$(cat ./.backend-url)"

log "Step 3/4: deploy frontend"
bash ./deploy-frontend.sh "$BACKEND_URL"
FRONTEND_URL="$(cat ./.frontend-url)"

log "Step 4/4: tightening backend CORS to $FRONTEND_URL"
resolve_project_id
gcloud run services update "$BACKEND_SERVICE" \
  --region "$REGION" \
  --project "$PROJECT_ID" \
  --update-env-vars "CORS_ORIGINS=$FRONTEND_URL"

cat <<EOF

$(_color '32' 'Deployed.')

  Control room:  $FRONTEND_URL
  Backend API:   $BACKEND_URL
  API docs:      $BACKEND_URL/docs

Open the control room URL and click "Inject demo anomaly" to drive a full
incident through the crew. See docs/deployment.md for how to attach Cloud
SQL, a real Grafana Cloud MCP endpoint, and Gemini credentials.
EOF
