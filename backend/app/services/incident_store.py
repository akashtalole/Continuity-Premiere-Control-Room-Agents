"""Firestore-backed persistence for incident data -- the UI-facing,
agent-written timeline. See app/firestore_db.py for the client/collection
constants and docs/agents.md#firestore-persistence for the schema
rationale.

Document shape:

  incidents/{incident_id}
    title, status, grafana_incident_id, workspace_id, opened_at, resolved_at,
    anomaly: {metric_name, observed_value, threshold, region, detected_at},
    remediation: {action_type, risk_level, approval_status, approved_by,
                  executed_at} | None,
    postmortem: {summary_markdown, timeline, generated_at} | None,

    agent_events/{event_id} (subcollection, one per crew step)
      agent_name, event_type, payload, created_at

    token_usage/{usage_id} (subcollection, one per agent turn)
      agent_name, input_tokens, output_tokens, created_at

`anomaly` and `remediation`/`postmortem` are single nested maps rather than
subcollections because this app's flow only ever writes one of each per
incident (one Sentinel detection kicks off a run, one Responder step, one
Wrap step) -- a subcollection would just add query overhead for a 1:1
relationship. `agent_events`/`token_usage` are genuinely repeated
per-incident, so those stay as ordered subcollections.

Queries here deliberately avoid combining an equality filter with a
server-side orderBy on a different field (list_incidents, find_similar_
incidents): Firestore requires a manually-created composite index for that
combination, and this app's incident volumes are demo/ops scale, so
filtering on the indexed field server-side and sorting the (small) result
set in Python avoids a manual GCP Console/gcloud step being a hard
prerequisite for the app to work at all.
"""

import uuid
from datetime import datetime, timezone
from typing import Any

from google.cloud.firestore import FieldFilter

from app.firestore_db import AGENT_EVENTS_SUBCOLLECTION, INCIDENTS_COLLECTION, TOKEN_USAGE_SUBCOLLECTION, get_firestore_client

_TERMINAL_STATUSES = ("postmortem_ready", "resolved", "skipped")


def _now() -> datetime:
    return datetime.now(timezone.utc)


async def create_incident(title: str, status: str, workspace_id: str, anomaly: dict[str, Any]) -> str:
    incident_id = str(uuid.uuid4())
    doc = {
        "title": title,
        "status": status,
        "grafana_incident_id": None,
        "workspace_id": workspace_id,
        "opened_at": _now(),
        "resolved_at": None,
        "anomaly": {
            "metric_name": anomaly["metric_name"],
            "observed_value": anomaly["observed_value"],
            "threshold": anomaly["threshold"],
            "region": anomaly["region"],
            "detected_at": _now(),
        },
        "remediation": None,
        "postmortem": None,
    }
    await get_firestore_client().collection(INCIDENTS_COLLECTION).document(incident_id).set(doc)
    return incident_id


async def set_status(incident_id: str, status: str, *, resolved: bool = False) -> None:
    update: dict[str, Any] = {"status": status}
    if resolved:
        update["resolved_at"] = _now()
    await get_firestore_client().collection(INCIDENTS_COLLECTION).document(incident_id).update(update)


async def set_grafana_incident_id(incident_id: str, grafana_incident_id: str | None) -> None:
    if not grafana_incident_id:
        return
    await get_firestore_client().collection(INCIDENTS_COLLECTION).document(incident_id).update(
        {"grafana_incident_id": grafana_incident_id}
    )


async def record_agent_event(incident_id: str, agent_name: str, event_type: str, payload: dict[str, Any]) -> None:
    event_id = str(uuid.uuid4())
    doc = {"agent_name": agent_name, "event_type": event_type, "payload": payload, "created_at": _now()}
    await (
        get_firestore_client()
        .collection(INCIDENTS_COLLECTION)
        .document(incident_id)
        .collection(AGENT_EVENTS_SUBCOLLECTION)
        .document(event_id)
        .set(doc)
    )


async def record_remediation(incident_id: str, resolution: dict[str, Any], approved_by: str | None) -> None:
    executed_at = resolution.get("executed_at")
    remediation = {
        "action_type": resolution.get("action_type", "unknown"),
        "risk_level": resolution.get("risk_level", "low"),
        "approval_status": resolution.get("approval_status", "not_required"),
        "approved_by": approved_by,
        "executed_at": datetime.fromisoformat(executed_at) if executed_at else None,
    }
    await get_firestore_client().collection(INCIDENTS_COLLECTION).document(incident_id).update(
        {"remediation": remediation}
    )


async def record_postmortem(incident_id: str, postmortem: dict[str, Any]) -> None:
    doc = {
        "summary_markdown": postmortem.get("summary_markdown", ""),
        "timeline": postmortem.get("timeline", []),
        "generated_at": _now(),
    }
    await get_firestore_client().collection(INCIDENTS_COLLECTION).document(incident_id).update({"postmortem": doc})


async def record_token_usage(incident_id: str, agent_name: str, input_tokens: int, output_tokens: int) -> None:
    usage_id = str(uuid.uuid4())
    doc = {
        "agent_name": agent_name,
        "input_tokens": input_tokens,
        "output_tokens": output_tokens,
        "created_at": _now(),
    }
    await (
        get_firestore_client()
        .collection(INCIDENTS_COLLECTION)
        .document(incident_id)
        .collection(TOKEN_USAGE_SUBCOLLECTION)
        .document(usage_id)
        .set(doc)
    )


async def get_incident_events(incident_id: str) -> list[dict[str, Any]]:
    """Ordered agent events for one incident -- the Wrap step's input, and
    part of get_incident()'s response below."""
    query = (
        get_firestore_client()
        .collection(INCIDENTS_COLLECTION)
        .document(incident_id)
        .collection(AGENT_EVENTS_SUBCOLLECTION)
        .order_by("created_at")
    )
    events = []
    async for doc in query.stream():
        data = doc.to_dict()
        data["id"] = doc.id
        events.append(data)
    return events


async def list_incidents(workspace_id: str | None = None) -> list[dict[str, Any]]:
    collection = get_firestore_client().collection(INCIDENTS_COLLECTION)
    query = collection.where(filter=FieldFilter("workspace_id", "==", workspace_id)) if workspace_id else collection
    incidents = [{"id": doc.id, **doc.to_dict()} async for doc in query.stream()]
    incidents.sort(key=lambda i: i["opened_at"], reverse=True)
    return incidents


async def get_incident(incident_id: str) -> dict[str, Any] | None:
    doc_ref = get_firestore_client().collection(INCIDENTS_COLLECTION).document(incident_id)
    snapshot = await doc_ref.get()
    if not snapshot.exists:
        return None
    data = {"id": snapshot.id, **snapshot.to_dict()}
    data["events"] = await get_incident_events(incident_id)
    data["token_usage"] = [doc.to_dict() async for doc in doc_ref.collection(TOKEN_USAGE_SUBCOLLECTION).stream()]
    return data


async def get_postmortem(incident_id: str) -> dict[str, Any] | None:
    snapshot = await get_firestore_client().collection(INCIDENTS_COLLECTION).document(incident_id).get()
    if not snapshot.exists:
        return None
    return (snapshot.to_dict() or {}).get("postmortem")


async def find_similar_incidents(metric_name: str, limit: int = 3) -> list[dict[str, Any]]:
    """Past resolved incidents with the same breaching metric, most recent
    first -- see app/adk_agents/memory_tools.py, the caller."""
    query = get_firestore_client().collection(INCIDENTS_COLLECTION).where(
        filter=FieldFilter("anomaly.metric_name", "==", metric_name)
    )
    docs = [doc.to_dict() async for doc in query.stream()]
    terminal = [d for d in docs if d.get("status") in _TERMINAL_STATUSES]
    terminal.sort(key=lambda d: d.get("opened_at") or _now(), reverse=True)

    results = []
    for d in terminal[:limit]:
        postmortem = d.get("postmortem") or {}
        remediation = d.get("remediation") or {}
        resolved_at = d.get("resolved_at")
        results.append(
            {
                "title": d.get("title"),
                "resolved_at": resolved_at.isoformat() if resolved_at else None,
                "action_taken": remediation.get("action_type"),
                "approval_status": remediation.get("approval_status"),
                "postmortem_excerpt": (postmortem.get("summary_markdown") or "")[:400],
            }
        )
    return results


async def analytics_summary() -> dict[str, Any]:
    """Cross-incident analytics for the history page. Fetches every
    incident (and, via a collection-group query, every token_usage
    subdocument across all incidents) and aggregates in Python -- fine at
    this app's incident volumes, and keeps the SQLite/Postgres-era
    behavior of aggregating client-side rather than relying on a specific
    backend's query features."""
    docs = [doc.to_dict() async for doc in get_firestore_client().collection(INCIDENTS_COLLECTION).stream()]

    by_status: dict[str, int] = {}
    breaches_by_metric: dict[str, int] = {}
    breaches_by_region: dict[str, int] = {}
    durations: list[float] = []
    for d in docs:
        status = d.get("status", "unknown")
        by_status[status] = by_status.get(status, 0) + 1

        anomaly = d.get("anomaly") or {}
        if anomaly.get("metric_name"):
            breaches_by_metric[anomaly["metric_name"]] = breaches_by_metric.get(anomaly["metric_name"], 0) + 1
        if anomaly.get("region"):
            breaches_by_region[anomaly["region"]] = breaches_by_region.get(anomaly["region"], 0) + 1

        opened_at, resolved_at = d.get("opened_at"), d.get("resolved_at")
        if opened_at is not None and resolved_at is not None:
            durations.append((resolved_at - opened_at).total_seconds())

    mttr_seconds = sum(durations) / len(durations) if durations else None

    total_input_tokens = 0
    total_output_tokens = 0
    async for usage_doc in get_firestore_client().collection_group(TOKEN_USAGE_SUBCOLLECTION).stream():
        usage = usage_doc.to_dict()
        total_input_tokens += usage.get("input_tokens", 0)
        total_output_tokens += usage.get("output_tokens", 0)

    return {
        "total_incidents": len(docs),
        "by_status": by_status,
        "mttr_seconds": mttr_seconds,
        "breaches_by_metric": breaches_by_metric,
        "breaches_by_region": breaches_by_region,
        "total_input_tokens": total_input_tokens,
        "total_output_tokens": total_output_tokens,
    }
