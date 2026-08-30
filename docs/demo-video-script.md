# Demo Video Script

3-minute shot list for the Devpost submission video, recorded against the live deployed app:

**https://premiere-control-room-web-sh76ssrjya-uc.a.run.app/**

This deployment is confirmed running the **real crew** — `GET /health` on its backend returns `agent_mode: "live"`, meaning real Gemini calls via Vertex AI and real Grafana Cloud MCP tool calls, not the deterministic mock crew. Say so on camera — it's the strongest claim this project can make, and it's true on this URL.

!!! warning "Known issue: verify Shot 4 works before recording"
    As of this doc's last check, injected incidents on this specific deployment were getting stuck at `investigating` and never progressing (the Detective step was failing silently — see `Orchestrator._run_crew`'s swallowed exception handler in `backend/app/orchestrator.py`). Confirm this is resolved (check `gcloud run services logs read premiere-control-room-backend --region <region> | grep -A 30 "Crew run failed"` for a traceback if not) and that the Grafana dashboard is provisioned (`infra/scripts/provision-grafana-dashboard.sh` — see [`infra/scripts/README.md`](https://github.com/akashtalole/Continuity-Premiere-Control-Room-Agents/blob/main/infra/scripts/README.md#provisioning-the-slo-dashboard)) before relying on Shot 4/5 working live on camera.

## Before recording

1. **Sign in once, off-camera, and confirm your admin credentials work.** Actions (inject anomaly, approve/reject) require an `operator` or `admin` account — see [Setup Guide](setup-guide.md) if you're locked out. **Don't type or read the password on camera.**
2. **Reset to a clean slate if you can.** A fresh deployment has zero incidents (`GET /api/analytics/summary` → `total_incidents: 0`) — ideal. If the deployment already has incidents on it, that's not fatal (real data is arguably a stronger look than a scripted empty state), but re-check Shot 3's framing ("all healthy, nothing running") against whatever's actually on screen.
3. **This is a real system, not a fixture — budget real wall-clock time.** Each agent turn is a real Gemini call plus real Grafana MCP tool calls; expect 5–25 seconds of visible "thinking" per step, not instant transitions. Two ways to handle this within a hard 3:00 cap:
   - **Record once, edit with speed ramps / jump cuts** over the waiting periods (recommended — keeps it honest, still fits the runtime).
   - **Record the live run first, unscripted, to see real timing**, then re-record narration to match the actual cut. Don't pre-script exact agent output text (root-cause hypothesis, brief wording) since the real crew's Gemini output varies run to run — the shots below cue off UI *state changes*, not literal on-screen text.
4. Open the app in a clean, logged-out browser window at ~1440×1000 for the cold open, then sign in on camera per Shot 3.
5. Have a second tab ready on the live Grafana Cloud stack (or skip Shot 5's deep-link if you'd rather not expose your Grafana org on camera — the embedded panel image alone still makes the point).

---

## Shot 1 — Cold open (0:00–0:15)

**Visual:** Black slate, then a title card: "Premiere Control Room — an agentic reliability engineer for live media premieres."

**Narration (≈13s spoken, rest is visual beat):**
> "A global streaming premiere breaks — CDN overload, encoder saturation, a bad origin deploy. Today, an engineer stares at a wall of dashboards while millions of viewers buffer. This is Premiere Control Room."

## Shot 2 — Five agents, fast (0:15–0:35)

**Visual:** The architecture diagram (see [`docs/architecture.md`](architecture.md)) or a simple five-name graphic (Sentinel → Detective → Producer → Responder → Wrap). Highlight each name as it's said.

**Narration:**
> "Five Google ADK agents, sharing one live Grafana Cloud MCP connection. Sentinel watches service-level objectives. Detective correlates metrics, logs, and traces into a root cause. Producer briefs the team in plain language. Responder proposes a fix. And Wrap writes the postmortem — automatically."

## Shot 3 — Sign in, live control room (0:35–0:50)

**Visual:** The real deployed app. Empty Control Room, all agent tiles idle, Live QoE map all green ("healthy"). Click **Sign in** in the sidebar, sign in as operator/admin (credentials off-screen).

**Narration:**
> "This isn't a mockup — it's live right now, running the real Gemini crew against a real Grafana Cloud stack. Everything's healthy. Let's break something."

## Shot 4 — The core loop, live (0:50–1:50)

**Visual:** Back on the Control Room page, signed in. Click **Inject demo anomaly**.

1. (0:50) Click the button; narrate as the **Agent activity feed** starts filling and the **Sentinel**/**Detective**/**Producer** status tiles light up blue ("running") one after another.
   > "Sentinel flags a real SLO breach. Detective pulls real metrics, logs, and traces through Grafana's MCP tools to build a root-cause hypothesis. Producer turns that into an incident brief."
2. (Whenever it lands — real Gemini latency, don't force a timestamp) the **Responder** tile turns amber, reading **blocked**, and the approval modal appears: *"1 of 1 pending"*, the proposed action type, and Approve/Reject buttons.
   > "And here's the moment that matters. Responder wants to act — but it's not allowed to. This isn't a prompt asking the model to be careful. It's a real function call, blocked in code, waiting on a human. The model can't talk its way past this."
3. Click **Approve** on camera.
   > "Approved."
4. Cut to the incident's status flipping through to **postmortem ready**, and the **Incident timeline** panel populating with the full agent-by-agent history.
   > "And Wrap closes it out — a full timeline and a written postmortem, generated the moment it resolves."

## Shot 5 — Proof it's real (1:50–2:10)

**Visual:** Scroll to the **Grafana panel** card on the incident — a live-rendered image pulled straight from the real Grafana dashboard, with an "Open in Grafana →" link. Click it to briefly show the real Grafana Cloud UI in a new tab (optional — skip if you'd rather not expose your Grafana org).

**Narration:**
> "That panel isn't a screenshot we baked in — it's rendered live from our own Grafana Cloud stack, the same one the agents just queried. This whole run — every model call, every tool call — is real."

## Shot 6 — Concurrency and playbooks (2:10–2:40)

**Visual:** Back on the Control Room home. Click **Inject 3 concurrent anomalies**.

1. Narrate over the feed as three incidents run in parallel and the Responder tile reads **blocked ×2** (or similar — however many land as high-risk simultaneously).
   > "Three incidents, three different playbooks. One's low-risk — the crew scales capacity and moves on by itself. Two are high-risk — CDN failover, a cache purge — and both wait for a human, tracked independently, one modal, one decision at a time."
2. Approve one, reject the other, on camera — quick cuts, no narration needed over the clicks themselves.
3. Let them settle to **postmortem ready** (or **skipped** for the rejected one).

## Shot 7 — History & analytics (2:40–2:55)

**Visual:** Click **History & Analytics** in the sidebar. Show the stat tiles: Total incidents, MTTR, Resolved, Active, and — distinctively — **Gemini input/output tokens** and **Estimated cost**.

**Narration:**
> "Every incident's archived automatically — mean time to resolution, breach frequency, and real Gemini token usage and cost, right down to the run we just watched."

## Shot 8 — Close (2:55–3:00)

**Visual:** Title card: "Google ADK · Gemini · Grafana Cloud MCP · FastAPI · Next.js" plus the live URL and repo link.

**Narration:**
> "Premiere Control Room. Reliability engineering that never blinks, and never acts alone."

---

## Notes for whoever's cutting this

- Total run time targets 3:00 flat. Shot 4 (the forced-approval gate) and Shot 6 (concurrent playbooks) are this project's two most differentiated claims — protect those if anything needs trimming, cut Shot 5 first if you're tight.
- Because this is a live system, exact wording of the Detective's hypothesis, the Producer's brief, and the Responder's proposed action will vary run to run — don't script narration around literal on-screen text; cue lines off UI *state* (tile color, modal appearing, badge count) as written above.
- Re-verify screen copy against the running app before your final cut — UI strings referenced here (`Inject demo anomaly`, `blocked`, `1 of N pending`, `postmortem ready`, the Live QoE map's `healthy`/`degraded`/`recovering` labels, the History page's stat tile labels) were pulled directly from the frontend source as of this repo's current commit.
