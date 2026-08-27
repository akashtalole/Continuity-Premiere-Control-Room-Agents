#!/usr/bin/env bash
# Optional: provisions a small Cloud SQL for PostgreSQL instance for real
# incident persistence. SQLite (deploy-backend.sh's default) lives on each
# Cloud Run instance's ephemeral filesystem and does not survive a
# redeploy or a cold start after the service scales to zero -- fine for a
# quick demo, not fine for anything you want to keep.
#
# Usage:
#   bash infra/scripts/provision-cloudsql.sh
#
# Then point the backend at it:
#   export CLOUDSQL_INSTANCE_CONNECTION_NAME="$(cat infra/scripts/.cloudsql-connection-name)"
#   export DATABASE_URL="postgresql+asyncpg://premiere:<password>@/premiere_control_room?host=/cloudsql/${CLOUDSQL_INSTANCE_CONNECTION_NAME}"
#   bash infra/scripts/deploy-backend.sh
#
# Override INSTANCE_NAME, TIER, DB_NAME, DB_USER, or DB_PASSWORD by
# exporting them before running this script.

set -euo pipefail
cd "$(dirname "${BASH_SOURCE[0]}")"
source ./lib.sh

require_command gcloud
resolve_project_id

: "${INSTANCE_NAME:=premiere-control-room-db}"
: "${TIER:=db-custom-1-3840}"
: "${DB_NAME:=premiere_control_room}"
: "${DB_USER:=premiere}"

if [[ -z "${DB_PASSWORD:-}" ]]; then
  if [[ -t 0 ]]; then
    read -r -s -p "Password for Cloud SQL user '$DB_USER': " DB_PASSWORD
    echo
  else
    require_command openssl
    DB_PASSWORD="$(openssl rand -base64 24)"
    warn "No DB_PASSWORD given; generated one (saved to infra/scripts/.cloudsql-password)."
  fi
fi
[[ -n "$DB_PASSWORD" ]] || die "A database password is required."

gcloud services enable sqladmin.googleapis.com --project "$PROJECT_ID"

if gcloud sql instances describe "$INSTANCE_NAME" --project "$PROJECT_ID" >/dev/null 2>&1; then
  log "Cloud SQL instance '$INSTANCE_NAME' already exists; skipping instance creation."
else
  log "Creating Cloud SQL Postgres instance '$INSTANCE_NAME' (tier=$TIER, region=$REGION) -- this takes several minutes"
  gcloud sql instances create "$INSTANCE_NAME" \
    --database-version=POSTGRES_15 \
    --tier="$TIER" \
    --region="$REGION" \
    --project "$PROJECT_ID"
fi

if gcloud sql databases describe "$DB_NAME" --instance "$INSTANCE_NAME" --project "$PROJECT_ID" >/dev/null 2>&1; then
  log "Database '$DB_NAME' already exists"
else
  log "Creating database '$DB_NAME'"
  gcloud sql databases create "$DB_NAME" --instance "$INSTANCE_NAME" --project "$PROJECT_ID"
fi

if gcloud sql users list --instance "$INSTANCE_NAME" --project "$PROJECT_ID" --format='value(name)' | grep -qx "$DB_USER"; then
  log "User '$DB_USER' already exists; updating password"
  gcloud sql users set-password "$DB_USER" --instance "$INSTANCE_NAME" --project "$PROJECT_ID" --password "$DB_PASSWORD"
else
  log "Creating user '$DB_USER'"
  gcloud sql users create "$DB_USER" --instance "$INSTANCE_NAME" --project "$PROJECT_ID" --password "$DB_PASSWORD"
fi

CONNECTION_NAME="$(gcloud sql instances describe "$INSTANCE_NAME" --project "$PROJECT_ID" --format='value(connectionName)')"
echo "$CONNECTION_NAME" > ./.cloudsql-connection-name
echo "$DB_PASSWORD" > ./.cloudsql-password
chmod 600 ./.cloudsql-password

DATABASE_URL="postgresql+asyncpg://${DB_USER}:${DB_PASSWORD}@/${DB_NAME}?host=/cloudsql/${CONNECTION_NAME}"

cat <<EOF

$(_color '32' 'Cloud SQL ready.')

  Instance connection name: $CONNECTION_NAME
  (saved to infra/scripts/.cloudsql-connection-name)
  Password saved to infra/scripts/.cloudsql-password (chmod 600) -- not committed to git, don't lose it.

Re-run the backend deploy against this database with:

  export CLOUDSQL_INSTANCE_CONNECTION_NAME="$CONNECTION_NAME"
  export DATABASE_URL="$DATABASE_URL"
  bash infra/scripts/deploy-backend.sh
EOF
