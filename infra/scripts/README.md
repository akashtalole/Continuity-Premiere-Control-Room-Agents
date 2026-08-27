# Deploying from Google Cloud Shell

These scripts take a fresh Google Cloud project from nothing to two live Cloud Run services (`premiere-control-room-backend`, `premiere-control-room-web`), each running as its own dedicated service account, with the backend authenticating to Gemini via Vertex AI (no API key needed). Meant to run from [Google Cloud Shell](https://cloud.google.com/shell) — gcloud is already authenticated there and pre-installed, so there's nothing to set up beyond a project.

## Quick start

```bash
# In Cloud Shell:
git clone https://github.com/akashtalole/Continuity-Premiere-Control-Room-Agents.git
cd Continuity-Premiere-Control-Room-Agents
gcloud config set project <YOUR_PROJECT_ID>

bash infra/scripts/deploy-all.sh
```

That's it — the script prints both service URLs at the end. With no other environment variables set, this deploys the real ADK agent crew (Gemini via Vertex AI) with the [deterministic mock crew](../../docs/agents.md#mock-crew-no-live-credentials-required) still active for the Grafana side until you provide `GRAFANA_URL` (see below) — a fully-functional live demo either way. `Ctrl+C` between steps is safe; every script is idempotent and can be re-run.

## What it does

1. **`00-setup.sh`** — one-time project setup:
   - Enables the Cloud Run, Cloud Build, Artifact Registry, Secret Manager, Vertex AI (`aiplatform.googleapis.com`), and IAM APIs.
   - Grants the Compute Engine default service account `roles/cloudbuild.builds.builder`, fixing a common Cloud Build permission gap on newer projects (`could not resolve source: ... storage.objects.get ... forbidden`) that otherwise fails every build before it starts.
   - Creates an Artifact Registry Docker repo.
   - Creates two dedicated service accounts (see below) and grants each its runtime IAM roles.
2. **`deploy-backend.sh`** — builds the backend image via Cloud Build, stores any credentials you provide in Secret Manager, and deploys to Cloud Run running as the backend service account, with `CORS_ORIGINS=*` (temporary — see step 4).
3. **`deploy-frontend.sh`** — builds the frontend image with the backend's real URL baked in as `NEXT_PUBLIC_API_URL`/`NEXT_PUBLIC_WS_URL` (Next.js inlines these at build time, so the backend must already be deployed), then deploys it to Cloud Run running as the frontend service account.
4. **`deploy-all.sh`** runs the three above in order, then tightens the backend's `CORS_ORIGINS` down to the frontend's actual URL — the two services need each other's URLs, so this two-pass approach is what resolves that.

Run them individually if you only need to redeploy one side (e.g. `bash infra/scripts/deploy-backend.sh` after a backend-only code change).

## Service accounts

`00-setup.sh` creates two service accounts and grants each only what it needs — neither service runs as the shared, broadly-privileged Compute Engine default service account:

| Service account | Used by | Roles granted |
|---|---|---|
| `premiere-backend@<project>.iam.gserviceaccount.com` | `premiere-control-room-backend` | `roles/aiplatform.user` (Gemini via Vertex AI), `roles/secretmanager.secretAccessor` (Grafana/OTLP secrets), `roles/cloudsql.client` (no-op unless Cloud SQL is attached), `roles/logging.logWriter`, `roles/monitoring.metricWriter` |
| `premiere-frontend@<project>.iam.gserviceaccount.com` | `premiere-control-room-web` | `roles/logging.logWriter`, `roles/monitoring.metricWriter` |

Override the account names with `BACKEND_SA_NAME` / `FRONTEND_SA_NAME` if you want something other than `premiere-backend` / `premiere-frontend`.

## Gemini access: Vertex AI by default, API key optional

The backend authenticates to Gemini as its own service account via Vertex AI and Application Default Credentials — `deploy-backend.sh` sets `GOOGLE_GENAI_USE_VERTEXAI=true`, `GOOGLE_CLOUD_PROJECT`, and `GOOGLE_CLOUD_LOCATION` automatically, and `00-setup.sh` already granted the backend service account `roles/aiplatform.user`. **No API key is required or stored anywhere in this path.**

If you'd rather use a Gemini Developer API key instead (e.g. to stay off Vertex AI quota), export `GOOGLE_API_KEY` before deploying — this switches the backend to the Developer API and stores the key in Secret Manager instead:

```bash
export GOOGLE_API_KEY="<your Gemini API key>"
bash infra/scripts/deploy-backend.sh
```

## Connecting real Grafana Cloud MCP

Grafana access is independent of the Gemini setup above — export these before running (they're written to Secret Manager, never left as plain Cloud Run env vars):

```bash
export GRAFANA_URL="https://<stack>.grafana.net"
export GRAFANA_SERVICE_ACCOUNT_TOKEN="<only if self-hosting mcp-grafana>"

bash infra/scripts/deploy-all.sh
```

Until `GRAFANA_URL` is set, the backend runs the deterministic mock crew regardless of the Gemini auth mode — see [`docs/agents.md`](../../docs/agents.md#mock-crew-no-live-credentials-required). If `GRAFANA_SERVICE_ACCOUNT_TOKEN`/`GOOGLE_API_KEY` are left unset and the shell is interactive, `deploy-backend.sh` prompts for them (input is not echoed); leave the prompt blank to skip.

## Persistence: SQLite vs. Cloud SQL

The default `DATABASE_URL` is SQLite, which lives on each Cloud Run instance's ephemeral filesystem — fine for a demo, but incident history does **not** survive a redeploy or a cold start after the service scales to zero. `deploy-backend.sh` detects this and pins the service to exactly one instance (`--min-instances=1 --max-instances=1`) so at least concurrent requests see consistent data, and prints a warning.

For real persistence, provision a small Cloud SQL for PostgreSQL instance first:

```bash
bash infra/scripts/provision-cloudsql.sh

export CLOUDSQL_INSTANCE_CONNECTION_NAME="$(cat infra/scripts/.cloudsql-connection-name)"
export DATABASE_URL="postgresql+asyncpg://premiere:$(cat infra/scripts/.cloudsql-password)@/premiere_control_room?host=/cloudsql/${CLOUDSQL_INSTANCE_CONNECTION_NAME}"
bash infra/scripts/deploy-backend.sh
```

The backend service account already has `roles/cloudsql.client` from `00-setup.sh`, so no extra IAM step is needed here.

## Real OpenTelemetry export

By default the [synthetic telemetry pipeline](../../docs/agents.md#synthetic-live-streaming-pipeline) only logs to the Cloud Run console. To actually land it in Grafana Cloud (Mimir/Loki/Tempo), export the standard OTel env vars before deploying:

```bash
export OTEL_EXPORTER_OTLP_ENDPOINT="https://otlp-gateway-prod-<region>.grafana.net/otlp"
export OTEL_EXPORTER_OTLP_HEADERS="Authorization=Basic $(echo -n '<instance_id>:<api_key>' | base64)"
bash infra/scripts/deploy-backend.sh
```

## Tearing down

```bash
bash infra/scripts/teardown.sh                        # deletes both Cloud Run services
bash infra/scripts/teardown.sh --with-cloudsql         # also deletes the Cloud SQL instance
bash infra/scripts/teardown.sh --with-service-accounts # also deletes the two service accounts
```

Flags can be combined. This leaves Artifact Registry images, Secret Manager secrets, and enabled APIs in place (cheap to keep, useful if you redeploy) — delete those manually with `gcloud artifacts repositories delete` / `gcloud secrets delete` if you want a completely clean project.

## Configuration reference

All scripts read the same base variables (all optional):

| Variable | Default | Notes |
|---|---|---|
| `PROJECT_ID` | `gcloud config get-value project` | |
| `REGION` | `us-central1` | Also used as the Vertex AI location |
| `REPO_NAME` | `premiere-control-room` | Artifact Registry repo name |
| `BACKEND_SERVICE` | `premiere-control-room-backend` | Cloud Run service name |
| `FRONTEND_SERVICE` | `premiere-control-room-web` | Cloud Run service name |
| `BACKEND_SA_NAME` | `premiere-backend` | Backend service account short name |
| `FRONTEND_SA_NAME` | `premiere-frontend` | Frontend service account short name |

See each script's header comment for the variables specific to it. The full environment variable reference for the app itself is in [`docs/deployment.md`](../../docs/deployment.md).
