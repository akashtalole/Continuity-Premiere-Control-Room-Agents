#!/usr/bin/env bash
# Shared helpers for the deploy scripts in this directory. Sourced, not run directly.
#
# Every script in infra/scripts/ is meant to run from Google Cloud Shell (or
# any machine with the gcloud CLI authenticated and a project already
# selected) with the repo checked out and backend/ + frontend/ present.

set -euo pipefail

# --- output helpers ---------------------------------------------------------

_color() { printf '\033[%sm%s\033[0m\n' "$1" "$2"; }
log()   { _color '36' "==> $*"; }
warn()  { _color '33' "!!  $*" >&2; }
die()   { _color '31' "xx  $*" >&2; exit 1; }

# --- config ------------------------------------------------------------------

# REGION / PROJECT_ID / REPO_NAME can be overridden by exporting them before
# running a script, e.g. `REGION=europe-west1 bash infra/scripts/deploy-all.sh`.
: "${REGION:=us-central1}"
: "${REPO_NAME:=premiere-control-room}"
: "${BACKEND_SERVICE:=premiere-control-room-backend}"
: "${FRONTEND_SERVICE:=premiere-control-room-web}"

resolve_project_id() {
  if [[ -n "${PROJECT_ID:-}" ]]; then
    return
  fi
  PROJECT_ID="$(gcloud config get-value project 2>/dev/null || true)"
  if [[ -z "$PROJECT_ID" || "$PROJECT_ID" == "(unset)" ]]; then
    die "No GCP project selected. Run 'gcloud config set project <PROJECT_ID>' first, or export PROJECT_ID=<id>."
  fi
  export PROJECT_ID
}

require_command() {
  command -v "$1" >/dev/null 2>&1 || die "'$1' is required but not found on PATH."
}

# repo_root: resolve the repository root from this script's location, so
# these scripts work regardless of the caller's current directory.
repo_root() {
  cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd
}

artifact_registry_host() {
  echo "${REGION}-docker.pkg.dev"
}

image_uri() {
  # image_uri <backend|web>
  echo "$(artifact_registry_host)/${PROJECT_ID}/${REPO_NAME}/$1:latest"
}

# ensure_secret <name>: creates the secret container if it doesn't exist yet
# (does NOT add a version -- see put_secret_value). Idempotent.
ensure_secret() {
  local name="$1"
  if gcloud secrets describe "$name" --project "$PROJECT_ID" >/dev/null 2>&1; then
    return
  fi
  log "Creating secret '$name'"
  gcloud secrets create "$name" --project "$PROJECT_ID" --replication-policy=automatic >/dev/null
}

# put_secret_value <name> <value>: adds a new version. No-op if value is empty.
put_secret_value() {
  local name="$1" value="$2"
  if [[ -z "$value" ]]; then
    return
  fi
  ensure_secret "$name"
  printf '%s' "$value" | gcloud secrets versions add "$name" --project "$PROJECT_ID" --data-file=- >/dev/null
  log "Stored a new version of secret '$name'"
}

# prompt_secret <env_var_name> <prompt_text>: if the named env var is already
# set (e.g. exported by the caller or CI), use it as-is; otherwise prompt
# interactively without echoing input. Leaves the var empty (not an error) if
# the user just presses enter -- callers decide whether that's acceptable.
prompt_secret() {
  local var_name="$1" prompt_text="$2"
  if [[ -n "${!var_name:-}" ]]; then
    return
  fi
  if [[ ! -t 0 ]]; then
    warn "$var_name is not set and this shell is non-interactive; leaving it empty."
    printf -v "$var_name" '%s' ""
    export "${var_name?}"
    return
  fi
  read -r -s -p "$prompt_text: " value
  echo
  printf -v "$var_name" '%s' "$value"
}
