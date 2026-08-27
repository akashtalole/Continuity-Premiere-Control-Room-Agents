#!/usr/bin/env bash
# Builds the frontend image (with the backend's URL baked in at build time --
# Next.js inlines NEXT_PUBLIC_* vars during `next build`) and deploys it to
# Cloud Run, running as the dedicated frontend service account created by
# 00-setup.sh (a minimal identity -- no Gemini/secrets access, since the
# frontend never talks to Grafana or Gemini directly).
#
# Usage:
#   bash infra/scripts/deploy-frontend.sh [backend-url]
#
# If backend-url is omitted, this reads infra/scripts/.backend-url, written
# by deploy-backend.sh -- run that first, or pass the URL explicitly:
#   bash infra/scripts/deploy-frontend.sh https://premiere-control-room-backend-xyz.a.run.app

set -euo pipefail
cd "$(dirname "${BASH_SOURCE[0]}")"
source ./lib.sh

require_command gcloud
resolve_project_id
ROOT="$(repo_root)"

BACKEND_URL="${1:-}"
if [[ -z "$BACKEND_URL" ]]; then
  if [[ -f "$ROOT/infra/scripts/.backend-url" ]]; then
    BACKEND_URL="$(cat "$ROOT/infra/scripts/.backend-url")"
  else
    die "No backend URL given and infra/scripts/.backend-url doesn't exist. Run deploy-backend.sh first, or pass the URL as an argument."
  fi
fi
[[ "$BACKEND_URL" == https://* ]] || die "backend URL must start with https:// (got: $BACKEND_URL)"

WS_URL="${BACKEND_URL/https:/wss:}/ws/control-room"

FRONTEND_SA_EMAIL="$(service_account_email "$FRONTEND_SA_NAME")"
if ! gcloud iam service-accounts describe "$FRONTEND_SA_EMAIL" --project "$PROJECT_ID" >/dev/null 2>&1; then
  die "Service account $FRONTEND_SA_EMAIL doesn't exist yet. Run infra/scripts/00-setup.sh first."
fi

IMAGE="$(image_uri web)"
log "Building frontend image: $IMAGE"
log "  NEXT_PUBLIC_API_URL=$BACKEND_URL"
log "  NEXT_PUBLIC_WS_URL=$WS_URL"

# --tag and --config are mutually exclusive on `gcloud builds submit`, and we
# need --build-arg (only available via a custom Cloud Build config), so
# generate a one-off cloudbuild.yaml rather than relying on --tag's implicit one.
CLOUDBUILD_CONFIG="$(mktemp)"
trap 'rm -f "$CLOUDBUILD_CONFIG"' EXIT
cat > "$CLOUDBUILD_CONFIG" <<EOF
steps:
  - name: gcr.io/cloud-builders/docker
    args:
      - build
      - --build-arg=NEXT_PUBLIC_API_URL=$BACKEND_URL
      - --build-arg=NEXT_PUBLIC_WS_URL=$WS_URL
      - --tag=$IMAGE
      - .
images:
  - $IMAGE
EOF

gcloud builds submit "$ROOT/frontend" --config "$CLOUDBUILD_CONFIG" --project "$PROJECT_ID"

log "Deploying $FRONTEND_SERVICE to Cloud Run ($REGION) as $FRONTEND_SA_EMAIL"
gcloud run deploy "$FRONTEND_SERVICE" \
  --image "$IMAGE" \
  --region "$REGION" \
  --project "$PROJECT_ID" \
  --platform managed \
  --service-account "$FRONTEND_SA_EMAIL" \
  --allow-unauthenticated \
  --memory 256Mi \
  --min-instances 0 \
  --max-instances 10

FRONTEND_URL="$(gcloud run services describe "$FRONTEND_SERVICE" \
  --region "$REGION" --project "$PROJECT_ID" --format='value(status.url)')"

log "Frontend deployed: $FRONTEND_URL"
echo "$FRONTEND_URL" > "$ROOT/infra/scripts/.frontend-url"
