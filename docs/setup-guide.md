# Setup Guide

Two paths, and they're not mutually exclusive: run it locally against the deterministic mock crew first (no credentials needed), then deploy the same code to Google Cloud Run when you're ready for the real Gemini + Grafana Cloud crew.

## 1. Local development

### Prerequisites

- Python 3.11+
- Node.js 18+
- No Gemini or Grafana account required to get started — the backend runs a deterministic mock agent crew by default.
- A **Firestore emulator**, though: incidents/agent events/postmortems/token usage (the UI-facing, agent-written data — see [Agent Layer → Firestore persistence](agents.md#firestore-persistence)) are read and written through Firestore unconditionally, mock crew or not. Users/audit-log/workspaces are still plain SQLite, no setup needed. See [Firestore](#firestore) below — it's one extra command, not a GCP account.

### Firestore

The backend needs *something* to talk to at `localhost:8081` before `uvicorn` will serve incident traffic. Start the emulator once per dev session, in its own terminal:

```bash
cd backend
npx --yes firebase-tools@latest emulators:start --only firestore
```

(Requires Node.js, already a prerequisite, and a JVM on `PATH` — the emulator itself is a Java process; `firebase-tools` downloads it on first run.) This reads `backend/firebase.json`/`backend/.firebaserc`, which pin it to port 8081 — the same port `backend/.env.example`'s `FIRESTORE_EMULATOR_HOST` points at and `tests/conftest.py` spawns its own copy of for `pytest`. Data lives only in the emulator's memory for that session; there's nothing to reset between runs beyond restarting it.

Prefer real GCP Firestore instead (e.g. to test against production-shaped data): leave `FIRESTORE_EMULATOR_HOST` unset in `.env`, run `gcloud auth application-default login`, and set `GOOGLE_CLOUD_PROJECT` to a project with a Firestore database already provisioned (`infra/scripts/00-setup.sh` does this for a deployed project — see [Deploying to Google Cloud Run](#2-deploying-to-google-cloud-run) below).

### Backend

```bash
cd backend
python3 -m venv .venv && . .venv/bin/activate
pip install -e ".[dev]"
cp .env.example .env
uvicorn app.main:app --reload --port 8000
```

(With the Firestore emulator from the previous step already running in another terminal.) The API is now live at `http://localhost:8000` (docs at `/docs`), running the mock crew — every route works, including the human-approval gate, without any Gemini/Grafana credentials. On first startup it also creates a `default` workspace and a bootstrap admin account; if you didn't set `ADMIN_PASSWORD` in `.env`, look for a line like this in the backend's console output:

```
No ADMIN_PASSWORD set -- generated one for admin@premiere.local: <random password>
```

That's your sign-in for the control room UI. See [User Guide → Signing in](user-guide.md#signing-in) for what roles unlock.

Run the test suite with `pytest` from `backend/` — 25 tests cover the full incident lifecycle, auth/audit, and cross-incident memory against the mock crew. `tests/conftest.py` spawns and tears down its own Firestore emulator automatically, so `pytest` needs no separate emulator running first (fine to run alongside `uvicorn`'s own emulator on 8081 — the two never run at the same moment in a normal workflow, but they'd only conflict if both grabbed port 8081 simultaneously).

### Frontend

```bash
cd frontend
npm install
cp .env.example .env.local
npm run dev
```

The control room is now live at `http://localhost:3000`, pointed at the backend above.

### Switching to the real agent crew locally

Set these in `backend/.env` to swap the mock crew for real Gemini + a real Grafana Cloud MCP connection:

```bash
# Gemini -- either an API key, or Vertex AI (gcloud auth application-default login first)
GOOGLE_API_KEY=<your Gemini API key>
# or:
GOOGLE_CLOUD_PROJECT=<project>
GOOGLE_GENAI_USE_VERTEXAI=true

# Grafana Cloud
GRAFANA_URL=https://<stack>.grafana.net
GRAFANA_SERVICE_ACCOUNT_TOKEN=<service account token, Editor role or higher>
```

Locally, the hosted `mcp.grafana.com` endpoint (the default) works fine — you can complete the one-time browser OAuth yourself. That stops being an option once you deploy somewhere unattended, which is exactly what the next section's `GRAFANA_MCP_ENDPOINT` step is for.

## 2. Deploying to Google Cloud Run

The scripts under `infra/scripts/` take a fresh GCP project to a live, publicly-reachable deployment, meant to run from [Google Cloud Shell](https://cloud.google.com/shell) (gcloud is already authenticated there).

```bash
git clone https://github.com/akashtalole/Continuity-Premiere-Control-Room-Agents.git
cd Continuity-Premiere-Control-Room-Agents
gcloud config set project <YOUR_PROJECT_ID>

bash infra/scripts/deploy-all.sh
```

With no other environment variables set, this deploys the real Gemini crew via Vertex AI (no API key needed — it uses the Cloud Run service account's own credentials) with the deterministic mock crew standing in for the Grafana side. You get a working, fully-functional live URL in a few minutes.

### Connecting real Grafana Cloud

Export these first, then re-run (or run for the first time):

```bash
export GRAFANA_URL="https://<stack>.grafana.net"
export GRAFANA_SERVICE_ACCOUNT_TOKEN="<service account token, Editor role or higher>"

bash infra/scripts/deploy-all.sh
```

This also deploys a small, separate Cloud Run service running the open-source `grafana/mcp-grafana` server — the hosted `mcp.grafana.com` endpoint only supports an interactive browser login, which doesn't work for an unattended backend, so a self-hosted instance is the documented answer for exactly this case. `deploy-all.sh` wires it up automatically; nothing to copy by hand. See [Agent Layer → Grafana MCP tool access](agents.md#grafana-mcp-tool-access) for why.

### Setting a real admin account (recommended before sharing the URL)

```bash
export ADMIN_EMAIL="you@yourteam.com"
export ADMIN_PASSWORD="<a real password>"
bash infra/scripts/deploy-backend.sh
```

This only takes effect against an **empty** users table -- the bootstrap admin is created once, on the first boot that finds no users at all, and never updated after. Export these *before* the service has ever booted (i.e. before the first `deploy-backend.sh`/`deploy-all.sh`), not as a way to change an existing admin's credentials later — that's not a thing this does. Skip this and a random password is generated for you on first boot instead — retrieve it from the Cloud Run service's logs (`gcloud run services logs read premiere-control-room-backend --region <region>`, look for the `ADMIN_PASSWORD` line) and sign in with `admin@premiere.local` and that password. There's no self-service password rotation yet; once signed in, use `POST /api/auth/users` (admin-only) to create the account you actually want.

### Everything else

Incident history persists in Firestore regardless (`infra/scripts/00-setup.sh` provisions it automatically). Real OpenTelemetry export to Grafana Cloud, Cloud SQL for persistent users/audit-log (SQLite is the default there and doesn't survive a redeploy), Slack/webhook notifications, and tearing the whole thing down are all covered in [`infra/scripts/README.md`](https://github.com/akashtalole/Continuity-Premiere-Control-Room-Agents/blob/main/infra/scripts/README.md) and the full [Deployment](deployment.md) reference — including every environment variable the backend reads.
