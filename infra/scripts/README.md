# Deploying from Google Cloud Shell

These scripts take a fresh Google Cloud project from nothing to two live Cloud Run services (`fastapi-backend`, `control-room-web`), and are meant to be run from [Google Cloud Shell](https://cloud.google.com/shell) — gcloud is already authenticated there and pre-installed, so there's nothing to set up beyond a project.

## Quick start

```bash
# In Cloud Shell:
git clone https://github.com/akashtalole/Agentic-Cinema-The-Blockbuster-Hackathon.git
cd Agentic-Cinema-The-Blockbuster-Hackathon
gcloud config set project <YOUR_PROJECT_ID>

bash infra/scripts/deploy-all.sh
```

That's it — the script prints both service URLs at the end. With no other environment variables set, this deploys the backend running the [deterministic mock crew](../../docs/agents.md#mock-crew-no-live-credentials-required) (no Gemini/Grafana credentials required), which is a fully-functional live demo. `Ctrl+C` between steps is safe; every script is idempotent and can be re-run.

## What it does

1. **`00-setup.sh`** — enables the Cloud Run, Cloud Build, Artifact Registry, and Secret Manager APIs; creates an Artifact Registry Docker repo.
2. **`deploy-backend.sh`** — builds the backend image via Cloud Build, stores any credentials you provide in Secret Manager, and deploys to Cloud Run with `CORS_ORIGINS=*` (temporary — see step 4).
3. **`deploy-frontend.sh`** — builds the frontend image with the backend's real URL baked in as `NEXT_PUBLIC_API_URL`/`NEXT_PUBLIC_WS_URL` (Next.js inlines these at build time, so the backend must already be deployed), then deploys it to Cloud Run.
4. **`deploy-all.sh`** runs the three above in order, then tightens the backend's `CORS_ORIGINS` down to the frontend's actual URL — the two services need each other's URLs, so this two-pass approach is what resolves that.

Run them individually if you only need to redeploy one side (e.g. `bash infra/scripts/deploy-backend.sh` after a backend-only code change).

## Connecting real Grafana Cloud MCP + Gemini

By default the backend runs the mock crew. To deploy the real agent crew, export these before running (they're written to Secret Manager, never left as plain Cloud Run env vars):

```bash
export GRAFANA_URL="https://<stack>.grafana.net"
export GOOGLE_API_KEY="<your Gemini API key>"
export GRAFANA_SERVICE_ACCOUNT_TOKEN="<only if self-hosting mcp-grafana>"

bash infra/scripts/deploy-all.sh
```

If you leave `GOOGLE_API_KEY`/`GRAFANA_SERVICE_ACCOUNT_TOKEN` unset and the shell is interactive, `deploy-backend.sh` prompts for them (input is not echoed). Leave the prompt blank to skip and stay on the mock crew.

## Persistence: SQLite vs. Cloud SQL

The default `DATABASE_URL` is SQLite, which lives on each Cloud Run instance's ephemeral filesystem — fine for a demo, but incident history does **not** survive a redeploy or a cold start after the service scales to zero. `deploy-backend.sh` detects this and pins the service to exactly one instance (`--min-instances=1 --max-instances=1`) so at least concurrent requests see consistent data, and prints a warning.

For real persistence, provision a small Cloud SQL for PostgreSQL instance first:

```bash
bash infra/scripts/provision-cloudsql.sh

export CLOUDSQL_INSTANCE_CONNECTION_NAME="$(cat infra/scripts/.cloudsql-connection-name)"
export DATABASE_URL="postgresql+asyncpg://premiere:$(cat infra/scripts/.cloudsql-password)@/premiere_control_room?host=/cloudsql/${CLOUDSQL_INSTANCE_CONNECTION_NAME}"
bash infra/scripts/deploy-backend.sh
```

## Real OpenTelemetry export

By default the [synthetic telemetry pipeline](../../docs/agents.md#synthetic-live-streaming-pipeline) only logs to the Cloud Run console. To actually land it in Grafana Cloud (Mimir/Loki/Tempo), export the standard OTel env vars before deploying:

```bash
export OTEL_EXPORTER_OTLP_ENDPOINT="https://otlp-gateway-prod-<region>.grafana.net/otlp"
export OTEL_EXPORTER_OTLP_HEADERS="Authorization=Basic $(echo -n '<instance_id>:<api_key>' | base64)"
bash infra/scripts/deploy-backend.sh
```

## Tearing down

```bash
bash infra/scripts/teardown.sh                 # deletes both Cloud Run services
bash infra/scripts/teardown.sh --with-cloudsql  # also deletes the Cloud SQL instance
```

This leaves Artifact Registry images and Secret Manager secrets in place (cheap to keep, useful if you redeploy) — delete those manually with `gcloud artifacts repositories delete` / `gcloud secrets delete` if you want a completely clean project.

## Configuration reference

All scripts read the same base variables (all optional):

| Variable | Default | Notes |
|---|---|---|
| `PROJECT_ID` | `gcloud config get-value project` | |
| `REGION` | `us-central1` | |
| `REPO_NAME` | `premiere-control-room` | Artifact Registry repo name |
| `BACKEND_SERVICE` | `premiere-control-room-backend` | Cloud Run service name |
| `FRONTEND_SERVICE` | `premiere-control-room-web` | Cloud Run service name |

See each script's header comment for the variables specific to it. The full environment variable reference for the app itself is in [`docs/deployment.md`](../../docs/deployment.md).
