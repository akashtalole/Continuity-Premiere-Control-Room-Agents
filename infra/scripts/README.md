# Deploying from Google Cloud Shell

These scripts take a fresh Google Cloud project from nothing to two live Cloud Run services (`premiere-control-room-backend`, `premiere-control-room-web`) -- three once you connect real Grafana Cloud credentials, which also stands up a self-hosted Grafana MCP server -- each running as its own dedicated service account, with the backend authenticating to Gemini via Vertex AI (no API key needed). Meant to run from [Google Cloud Shell](https://cloud.google.com/shell) — gcloud is already authenticated there and pre-installed, so there's nothing to set up beyond a project.

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
   - Creates three dedicated service accounts (see below) and grants each its runtime IAM roles.
2. **`deploy-mcp-grafana.sh`** — deploys the open-source `grafana/mcp-grafana` server to its own Cloud Run service, running as the mcp-grafana service account. Only runs (from `deploy-all.sh`) when `GRAFANA_URL` is set; see [Connecting real Grafana Cloud MCP](#connecting-real-grafana-cloud-mcp) below for why this exists.
3. **`deploy-backend.sh`** — builds the backend image via Cloud Build, stores any credentials you provide in Secret Manager, and deploys to Cloud Run running as the backend service account, with `CORS_ORIGINS=*` (temporary — see step 5).
4. **`deploy-frontend.sh`** — builds the frontend image with the backend's real URL baked in as `NEXT_PUBLIC_API_URL`/`NEXT_PUBLIC_WS_URL` (Next.js inlines these at build time, so the backend must already be deployed), then deploys it to Cloud Run running as the frontend service account.
5. **`deploy-all.sh`** runs the four above in order, then tightens the backend's `CORS_ORIGINS` down to the frontend's actual URL — the two app services need each other's URLs, so this two-pass approach is what resolves that.

Run them individually if you only need to redeploy one part (e.g. `bash infra/scripts/deploy-backend.sh` after a backend-only code change).

## Service accounts

`00-setup.sh` creates three service accounts and grants each only what it needs — none of these services runs as the shared, broadly-privileged Compute Engine default service account:

| Service account | Used by | Roles granted |
|---|---|---|
| `premiere-backend@<project>.iam.gserviceaccount.com` | `premiere-control-room-backend` | `roles/aiplatform.user` (Gemini via Vertex AI), `roles/secretmanager.secretAccessor` (Grafana/OTLP secrets), `roles/cloudsql.client` (no-op unless Cloud SQL is attached), `roles/logging.logWriter`, `roles/monitoring.metricWriter` |
| `premiere-frontend@<project>.iam.gserviceaccount.com` | `premiere-control-room-web` | `roles/logging.logWriter`, `roles/monitoring.metricWriter` |
| `premiere-mcp-grafana@<project>.iam.gserviceaccount.com` | `premiere-control-room-mcp-grafana` | `roles/secretmanager.secretAccessor` (its two secrets), `roles/logging.logWriter`, `roles/monitoring.metricWriter` |

Override the account names with `BACKEND_SA_NAME` / `FRONTEND_SA_NAME` / `MCP_GRAFANA_SA_NAME` if you want something other than the defaults above.

## Gemini access: Vertex AI by default, API key optional

The backend authenticates to Gemini as its own service account via Vertex AI and Application Default Credentials — `deploy-backend.sh` sets `GOOGLE_GENAI_USE_VERTEXAI=true`, `GOOGLE_CLOUD_PROJECT`, and `GOOGLE_CLOUD_LOCATION` automatically, and `00-setup.sh` already granted the backend service account `roles/aiplatform.user`. **No API key is required or stored anywhere in this path.**

If you'd rather use a Gemini Developer API key instead (e.g. to stay off Vertex AI quota), export `GOOGLE_API_KEY` before deploying — this switches the backend to the Developer API and stores the key in Secret Manager instead:

```bash
export GOOGLE_API_KEY="<your Gemini API key>"
bash infra/scripts/deploy-backend.sh
```

## Connecting real Grafana Cloud MCP

Grafana access is independent of the Gemini setup above. It takes one extra Cloud Run service because of how Grafana's two MCP servers authenticate (see [`docs/agents.md`](../../docs/agents.md#grafana-mcp-tool-access) for the full reasoning):

- The **hosted** server (`https://mcp.grafana.com/mcp`) only supports an interactive, browser-based OAuth 2.1 login. There's no service-account option, so nothing can drive it from an unattended Cloud Run backend.
- The **self-hosted**, open-source `grafana/mcp-grafana` server is the documented answer for exactly this case — authenticated with a Grafana service-account token instead. `deploy-mcp-grafana.sh` deploys it for you.

**1. Create a Grafana Cloud stack** (skip if you already have one): [grafana.com/products/cloud](https://grafana.com/products/cloud/), free tier is enough — see the [account creation guide](https://grafana.com/docs/grafana-cloud/get-started/create-account/).

**2. Create a service account token** in that stack: Administration → Service accounts → new account with the **Editor** role (or higher) → add a token. This grants it MCP tool access to query Prometheus/Loki/Tempo and write to Incidents/Alerting/Annotations — exactly the tool surface the crew uses (see [`low-level-design.md`](../../docs/low-level-design.md#grafana-mcp-tool-mapping) for the full per-agent tool list).

**3. Deploy**, with `GRAFANA_URL` set so `deploy-all.sh` picks up the extra step automatically:

```bash
export GRAFANA_URL="https://<stack>.grafana.net"
export GRAFANA_SERVICE_ACCOUNT_TOKEN="<the token from step 2>"

bash infra/scripts/deploy-all.sh
```

This deploys `premiere-control-room-mcp-grafana` first (public on Cloud Run, but gated by an auto-generated caller-auth token — see [`docs/security.md`](../../docs/security.md)), then wires its URL and that token into the backend automatically. Nothing to copy by hand, and re-running `deploy-all.sh` later reuses the same generated token rather than rotating it out from under an already-deployed backend.

Until `GRAFANA_URL` is set, the backend runs the deterministic mock crew regardless of the Gemini auth mode — see [`docs/agents.md`](../../docs/agents.md#mock-crew-no-live-credentials-required). If `GRAFANA_SERVICE_ACCOUNT_TOKEN`/`GOOGLE_API_KEY` are left unset and the shell is interactive, `deploy-backend.sh`/`deploy-mcp-grafana.sh` prompt for them (input is not echoed); leave the prompt blank to skip (deploy-mcp-grafana.sh requires it, though -- there's no mock mode for that script specifically).

Once it's live, every Sentinel/Detective/Producer/Responder/Wrap MCP tool call is a real call against your stack — and, per the next section, you also get to *watch* those calls happen in Grafana Cloud's own AI Observability app.

### Bonus: the agent crew's own telemetry in Grafana Cloud AI Observability

This is a "for free" side effect worth demoing on its own: `google-adk` has built-in OpenTelemetry instrumentation for every LLM call and every MCP tool call, and it rides the same OTLP pipeline as [Real OpenTelemetry export](#real-opentelemetry-export) below with zero extra setup. Once `OTEL_EXPORTER_OTLP_ENDPOINT`/`OTEL_EXPORTER_OTLP_HEADERS` are set, open Grafana Cloud's [AI Observability](https://grafana.com/docs/grafana-cloud/machine-learning/ai-observability/) app to see real Gemini call latency/token usage and real Grafana MCP tool spans from the live crew — see [`docs/agents.md`](../../docs/agents.md#ai-observability-the-agent-crews-own-telemetry-for-free).

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
bash infra/scripts/teardown.sh                        # deletes all Cloud Run services (mcp-grafana too, if deployed)
bash infra/scripts/teardown.sh --with-cloudsql         # also deletes the Cloud SQL instance
bash infra/scripts/teardown.sh --with-service-accounts # also deletes the three service accounts
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
| `MCP_GRAFANA_SERVICE` | `premiere-control-room-mcp-grafana` | Cloud Run service name |
| `BACKEND_SA_NAME` | `premiere-backend` | Backend service account short name |
| `FRONTEND_SA_NAME` | `premiere-frontend` | Frontend service account short name |
| `MCP_GRAFANA_SA_NAME` | `premiere-mcp-grafana` | mcp-grafana service account short name |

See each script's header comment for the variables specific to it. The full environment variable reference for the app itself is in [`docs/deployment.md`](../../docs/deployment.md).
