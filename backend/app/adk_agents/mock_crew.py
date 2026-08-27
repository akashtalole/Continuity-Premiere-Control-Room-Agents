"""Deterministic stand-ins for the ADK crew, used when no Gemini API key /
Grafana stack is configured (settings.agents_configured is False).

This keeps the FastAPI backend, orchestrator, persistence, WebSocket feed,
and control room UI fully exercisable end-to-end -- including the real
human-approval gate in approval.py and the multi-scenario playbook table in
playbooks.py -- without live credentials. Swap in the real AgentInvoker-
backed crew (see agents.py / runner.py) by setting GOOGLE_API_KEY and
GRAFANA_URL.
"""

import asyncio
from datetime import datetime
from typing import Any, Protocol

from app.adk_agents.approval import request_human_approval
from app.adk_agents.memory_tools import find_similar_incidents
from app.adk_agents.playbooks import select_playbook

UPSTREAM_BY_METRIC: dict[str, list[str]] = {
    "rebuffer_ratio": ["edge-cache", "origin-shield"],
    "origin_error_rate": ["origin-shield", "transcoder-pool"],
    "playback_failure_rate": ["player-web", "drm-license-service"],
    "encoder_queue_depth": ["live-encoder-pool"],
    "cache_hit_ratio": ["edge-cache"],
}


class Invoker(Protocol):
    async def run(self, incident_id: str, input_data: dict[str, Any]) -> dict[str, Any]: ...


class MockDetectiveInvoker:
    async def run(self, incident_id: str, input_data: dict[str, Any]) -> dict[str, Any]:
        await asyncio.sleep(0.2)
        metric = input_data.get("metric_name", "rebuffer_ratio")
        region = input_data.get("region", "us-east-1")
        upstream = UPSTREAM_BY_METRIC.get(metric, ["edge-cache"])

        # Real DB lookup (not canned) -- see memory_tools.py. Gives the mock
        # crew the same "have we seen this before" behavior the real
        # Detective gets from its find_similar_incidents tool, so the
        # feature is demoable without live Gemini/Grafana credentials.
        precedents = await find_similar_incidents(metric, limit=3)
        confidence = 0.82
        summary = (
            f"Correlated a spike in '{metric}' in {region} with anomalous behavior in "
            f"{' and '.join(upstream)}."
        )
        if precedents:
            confidence = min(0.95, confidence + 0.05 * len(precedents))
            summary += (
                f" This is the {_ordinal(len(precedents) + 1)} time '{metric}' has breached; "
                f"last time the fix was {precedents[0].get('action_taken') or 'unresolved'}."
            )

        return {
            "summary": summary,
            "confidence": confidence,
            "upstream_services": upstream,
            "supporting_trace_ids": ["trace-7f1a9c", "trace-7f1a9d"],
            "supporting_log_query": f'{{service="{upstream[0]}", region="{region}"}} |= "error"',
        }


def _ordinal(n: int) -> str:
    if 10 <= n % 100 <= 20:
        suffix = "th"
    else:
        suffix = {1: "st", 2: "nd", 3: "rd"}.get(n % 10, "th")
    return f"{n}{suffix}"


class MockProducerInvoker:
    async def run(self, incident_id: str, input_data: dict[str, Any]) -> dict[str, Any]:
        await asyncio.sleep(0.2)
        metric = input_data.get("metric_name", "rebuffer_ratio")
        region = input_data.get("region", "us-east-1")
        summary = input_data.get("summary", f"Elevated {metric} detected during the premiere broadcast.")
        return {
            "grafana_incident_id": f"INC-{incident_id[:8]}",
            "title": f"SLO breach: {metric} in {region}",
            "plain_language_summary": (
                f"Viewers in {region} are affected. Root cause: {summary} "
                "On-call has been paged and a fix is being prepared."
            ),
            "severity": "sev2",
            "oncall_user": "oncall-engineer",
        }


class MockResponderInvoker:
    async def run(self, incident_id: str, input_data: dict[str, Any]) -> dict[str, Any]:
        playbook = select_playbook(input_data.get("metric_name"))
        action_description = playbook["description"]
        risk_level = playbook["risk_level"]

        if risk_level == "high":
            approval_status = await request_human_approval(
                incident_id=incident_id, action_description=action_description, risk_level=risk_level
            )
        else:
            # Low-risk actions execute directly, per docs/low-level-design.md's
            # state machine (Briefed -> Remediating, no AwaitingApproval hop).
            approval_status = "approved"

        executed_at = None
        if approval_status == "approved":
            await asyncio.sleep(0.2)
            executed_at = datetime.utcnow().isoformat()

        return {
            "action_type": playbook["action_type"],
            "risk_level": risk_level,
            "description": action_description,
            "approval_status": approval_status if risk_level == "high" else "not_required",
            "approved_by": "oncall-engineer" if approval_status == "approved" else None,
            "executed_at": executed_at,
        }


class MockWrapInvoker:
    async def run(self, incident_id: str, input_data: dict[str, Any]) -> dict[str, Any]:
        await asyncio.sleep(0.2)
        events: list[dict[str, Any]] = input_data.get("events", [])
        title = input_data.get("title", "Incident")
        resolution = input_data.get("resolution", {})
        timeline = [
            {"agent": e.get("agent_name"), "event": e.get("event_type"), "at": e.get("created_at")} for e in events
        ]

        if resolution.get("approval_status") in ("approved", "not_required"):
            outcome = (
                f"**{resolution.get('action_type', 'the proposed action')}** was executed "
                f"({resolution.get('description', '')}); the affected SLO returned to baseline within minutes."
            )
        else:
            outcome = "The proposed remediation was not executed; the incident was left for manual follow-up."

        return {
            "summary_markdown": (
                f"# Postmortem\n\n**Incident:** {title}\n\n## Timeline\n"
                + "\n".join(f"- `{t['at']}` **{t['agent']}** — {t['event']}" for t in timeline)
                + f"\n\n## Resolution\n{outcome}\n"
            ),
            "timeline": timeline,
        }


def build_mock_crew() -> dict[str, Invoker]:
    return {
        "detective": MockDetectiveInvoker(),
        "producer": MockProducerInvoker(),
        "responder": MockResponderInvoker(),
        "wrap": MockWrapInvoker(),
    }
