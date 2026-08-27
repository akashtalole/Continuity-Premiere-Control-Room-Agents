# Demo Video Script

A timed shot list for the hackathon's 3-minute submission video (`docs/build-plan.md`'s milestone 8). Every UI state referenced below has been verified working in this repo — record against the real running app, not a mockup.

**Before recording:**
1. If you have real Grafana Cloud + Gemini credentials, set `GOOGLE_API_KEY` and `GRAFANA_URL` in `backend/.env` and use those instead of the mock crew — see the callout in Shot 4 for exactly what changes. If you don't have them yet, the mock-crew recording below is still an honest demo: say so on screen (a caption like "shown here with the deterministic offline crew — see README for the live-Grafana run") rather than implying it's live when it isn't.
2. Start both apps fresh: `cd backend && uvicorn app.main:app --port 8000` and `cd frontend && npm run dev`.
3. Open `http://localhost:3000` in a clean browser window at a decent size (~1400×1000 records well) with no other incidents in the database (delete `backend/premiere_control_room.db` if this isn't the first run).

---

## Shot 1 — Cold open (0:00–0:15)

**Visual:** Black slate, then title card: "Premiere Control Room — an agentic reliability engineer for live media premieres."

**Narration:**
> "A global streaming premiere breaks — CDN overload, encoder saturation, a bad origin deploy. Today, an engineer stares at a wall of Grafana dashboards while millions of viewers buffer. This is Premiere Control Room: five AI agents that detect, diagnose, brief, and fix it — with a human still in charge of every risky decision."

## Shot 2 — Architecture, fast (0:15–0:35)

**Visual:** The HLD/LLD architecture diagram (from the original spec, or `docs/architecture.md`'s mermaid diagram rendered). Highlight the five agent names as you say them.

**Narration:**
> "Five Google ADK agents share one Grafana Cloud MCP connection. Sentinel watches SLOs. Detective correlates metrics, logs, and traces. Producer briefs the Studio Head in plain language. Responder proposes a fix — and Wrap writes the postmortem automatically."

## Shot 3 — The core loop, live (0:35–1:40)

**Visual:** Control room UI at `http://localhost:3000`, empty state.

1. (0:35) Point at the empty **Live QoE map** and **Incidents** panel — "all healthy, nothing running yet."
2. (0:40) Click **Inject demo anomaly**.
3. (0:45–0:55) Narrate the feed as events land in **Agent Activity Feed**: "Sentinel flags an SLO breach → Detective correlates a root cause → Producer opens an incident brief." Point at the **Live QoE map** tile flipping to "Degraded."
4. (1:00) The **Approval Modal** appears ("Responder wants to take a high-risk action"). Pause here.

   > "This is the governance moment. The Responder can't touch anything — it's blocked on a real function call that only a human can resolve. Not a prompt asking it to be careful — code that makes it wait."

5. (1:10) Click **Approve**.
6. (1:15–1:35) Show the incident flipping through to **Postmortem ready**, the timeline populating in **Incident Timeline**, and the QoE tile going to "Recovering."
7. (1:35) Quick cut to the **Incident Timeline** panel showing the full agent-by-agent history for this one incident.

## Shot 4 — What's actually running underneath (1:40–2:00)

**Visual:** Split-screen or quick cut to a terminal.

- **If using real Grafana/Gemini credentials:** show the backend terminal log lines where the ADK Runner is actually calling Grafana MCP tools (`query_prometheus`, `create_incident`, etc.) — this is the moment that proves "real runtime MCP use," so don't skip it if you have it.
- **If using the mock crew:** show the terminal running `uvicorn app.main:app` with `agent_mode: "mock"` visible in a `GET /health` response, and say so explicitly:
  > "This run is the deterministic offline crew, so the demo works without live credentials — swap in a Grafana Cloud API key and it's the same code path talking to the real MCP server."
- Either way, cut briefly to the synthetic telemetry pipeline's console output (`docs/build-plan.md`'s telemetry stub) showing real OpenTelemetry metric/trace export — proof the SLO data itself isn't fake.

## Shot 5 — Advanced: playbooks + concurrency (2:00–2:35)

**Visual:** Back in the UI.

1. (2:00) Click **Inject 3 concurrent anomalies**.
2. (2:05–2:15) Narrate over the feed: "Three incidents, three different playbooks. Encoder capacity scales itself automatically — that's low risk. The CDN failover and cache purge both wait for approval — high risk, one human decision at a time, tracked independently." Point at the **Responder ×2 — Blocked** badge and the approval modal's "1 of 2 pending" counter.
3. (2:20) Approve one, reject the other, on camera.
4. (2:30) Let all three settle to **Postmortem ready**.

## Shot 6 — History & analytics (2:35–2:50)

**Visual:** Click **History & analytics**.

**Narration:**
> "Every incident is archived automatically — MTTR, breach frequency by metric and region, and the full postmortem, one click away."

Click into one incident row to show the postmortem expanding inline.

## Shot 7 — Close (2:50–3:00)

**Visual:** Title card again, with a short tech-stack line: "Google ADK · Gemini · Grafana Cloud MCP · FastAPI · Next.js" and the repo URL.

**Narration:**
> "Premiere Control Room — reliability engineering that never blinks, and never acts alone."

---

## Notes for whoever's cutting this

- Total run time targets 3:00 flat; Shots 3 and 5 are the ones worth protecting if something has to be trimmed — they're the only two that show the forced-approval gate and the multi-scenario playbook, which are this project's two strongest, most differentiated claims.
- Every screen state named above (the approval modal copy, the "×2 Blocked" badge, the "1 of 2 pending" counter, the QoE map's Degraded/Recovering/Healthy labels, the History page's stat tiles) is exact text from the running app as of this repo's current commit — if the UI changes, re-check this script against it before recording.
