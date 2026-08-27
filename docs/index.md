# Premiere Control Room

**An agentic reliability engineer for live media premieres**, built on the Google Agent Development Kit (ADK), Gemini, and the Grafana Cloud MCP server.

Live, unrepeatable media events — streaming premieres, award shows, live sports — break in ways that used to mean an engineer staring at a wall of Grafana dashboards under pressure. Premiere Control Room replaces that manual loop with a crew of five ADK agents — **Sentinel, Detective, Producer, Responder, Wrap** — that detect, correlate, brief, remediate, and document an incident automatically, with a forced human-approval gate before anything state-changing happens.

<div class="grid cards" markdown>

- :material-rocket-launch:{ .lg .middle } **New here? Start with the Setup Guide**

    ---

    Get the backend and frontend running locally, then deploy to Google Cloud Run.

    [:octicons-arrow-right-24: Setup Guide](setup-guide.md)

- :material-account:{ .lg .middle } **Already deployed? Read the User Guide**

    ---

    Signing in, roles, injecting incidents, approving remediations, reading the timeline.

    [:octicons-arrow-right-24: User Guide](user-guide.md)

- :material-sitemap:{ .lg .middle } **How it's built**

    ---

    The agent crew, the FastAPI backend, the Next.js control room, and the design decisions behind them.

    [:octicons-arrow-right-24: Overview](overview.md) · [:octicons-arrow-right-24: Architecture](architecture.md)

- :material-shield-lock:{ .lg .middle } **Security & governance**

    ---

    Role-based access control, the audit log, least-privilege Grafana MCP scoping, and secrets handling.

    [:octicons-arrow-right-24: Security & Governance](security.md)

</div>

## What's in the crew

| Agent | Role |
|---|---|
| **Sentinel** | Continuously monitors SLOs (rebuffer ratio, playback failure rate, origin error rate, encoder queue depth) and detects anomalies |
| **Detective** | Correlates signals across metrics, logs, and traces into a root-cause hypothesis, checking whether the same failure has happened before |
| **Producer** | Turns the finding into an executive-friendly incident brief and identifies who's on call |
| **Responder** | Proposes and executes remediation — high-risk actions always wait for human approval |
| **Wrap** | Generates the incident timeline and a downloadable postmortem report |

## Source

The full source is on [GitHub](https://github.com/akashtalole/Continuity-Premiere-Control-Room-Agents). Documentation source lives under [`docs/`](https://github.com/akashtalole/Continuity-Premiere-Control-Room-Agents/tree/main/docs) in that repo — edits are welcome via pull request.
