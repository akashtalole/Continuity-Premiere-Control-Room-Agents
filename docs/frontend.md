# Frontend — Control Room Web App

## Routes

| Route | Contents |
|---|---|
| `/` | `ControlRoomPage` — the live control room (see component tree below) |
| `/history` | `HistoryPage` — searchable incident archive + cross-incident analytics, backed by `GET /api/analytics/summary` |

## Component tree

```
<ControlRoomPage>
 ├── <LiveQoEMap />            — region-colored map of rebuffer / error rate
 ├── <AgentActivityFeed />     — streaming log of sentinel/detective/producer/responder/wrap events
 ├── <IncidentTimeline />      — chronological view of one incident, built from AGENT_EVENT rows
 ├── <ApprovalModal />         — appears on responder_action_pending; a *queue* of pending approvals,
 │                               one modal at a time with a "N pending" badge, since concurrent
 │                               incidents can each generate their own high-risk approval request
 └── <GrafanaPanelEmbed />     — renders get_panel_image output + generate_deeplink "open in Grafana"
```

The header also carries an **Inject 3 concurrent anomalies** button (alongside the single-incident **Inject demo anomaly**) that fires three different metric/region scenarios in parallel via `Promise.all`, specifically to exercise the queued-approval and per-incident agent-status paths -- see [`low-level-design.md`](low-level-design.md#concurrent-incidents). Agent status badges show `×N` when an agent has more than one incident active.

## Approval queue (sketch)

```typescript
// frontend/app/page.tsx (abridged)
const [pendingApprovals, setPendingApprovals] = useState<PendingApproval[]>([]);

// on a responder_action_pending WS event:
setPendingApprovals((prev) =>
  prev.some((p) => p.incidentId === entry.incidentId) ? prev : [...prev, entry]
);

// ApprovalModal shows queue[0] and a "1 of N pending" badge when N > 1;
// onResolved removes that incident from the queue so the next one surfaces.
```

## WebSocket hook (sketch)

```typescript
// frontend/lib/useControlRoomSocket.ts
import { useEffect, useState } from "react";

export type AgentEvent = {
  type: string;
  incident_id: string;
  agent: string;
  timestamp: string;
  payload: Record<string, unknown>;
};

export function useControlRoomSocket(url: string) {
  const [events, setEvents] = useState<AgentEvent[]>([]);

  useEffect(() => {
    const ws = new WebSocket(url);
    ws.onmessage = (msg) => setEvents((prev) => [...prev, JSON.parse(msg.data)]);
    const heartbeat = setInterval(() => ws.readyState === 1 && ws.send("ping"), 15000);
    return () => {
      clearInterval(heartbeat);
      ws.close();
    };
  }, [url]);

  return events;
}
```

The frontend consumes the `AgentEventEnvelope` wire format documented in [`backend.md`](backend.md#websocket-event-contract), which mirrors the `/api/incidents/*` REST responses so the UI can be reconstructed on page load without replaying the WebSocket stream from the start.

## History & analytics page

`/history` fetches `GET /api/incidents` (client-side filtered by title/status) and `GET /api/analytics/summary`, rendering:

- Stat tiles: total incidents, MTTR, resolved count, active count.
- Two breach-frequency bar lists (by metric, by region), built from `AnalyticsSummary.breaches_by_metric` / `breaches_by_region`.
- A searchable/filterable incident list where clicking a row lazily fetches and expands that incident's postmortem (`GET /api/incidents/{id}/postmortem`).
