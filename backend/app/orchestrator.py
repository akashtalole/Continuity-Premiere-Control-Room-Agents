"""Drives one incident through the Sentinel(already-detected) -> Detective ->
Producer -> Responder -> Wrap loop, persisting every step and streaming it
to the control room UI over WebSocket.

See docs/low-level-design.md for the state machine and sequence diagram
this module implements, and docs/agents.md for the underlying agent crew.
"""

import logging
from datetime import datetime
from uuid import UUID

from sqlalchemy import select

from app.adk_agents.approval import resolve_approval
from app.adk_agents.crew import get_crew
from app.adk_agents.playbooks import select_playbook
from app.db import session_scope
from app.models.db import AgentEventRow, AnomalyEventRow, Incident, PostmortemRow, RemediationActionRow
from app.models.schemas import AgentEventEnvelope, IncidentStatus
from app.services import agent_status
from app.ws.manager import manager

logger = logging.getLogger(__name__)


class Orchestrator:
    async def start_incident(self, anomaly: dict) -> UUID:
        """Persist the Sentinel-detected anomaly as a new incident and kick off the crew."""
        async with session_scope() as db:
            incident = Incident(
                title=f"SLO breach: {anomaly['metric_name']} in {anomaly['region']}",
                status=IncidentStatus.anomaly_detected.value,
            )
            db.add(incident)
            await db.flush()

            db.add(
                AnomalyEventRow(
                    incident_id=incident.id,
                    metric_name=anomaly["metric_name"],
                    observed_value=anomaly["observed_value"],
                    threshold=anomaly["threshold"],
                    region=anomaly["region"],
                )
            )
            await db.commit()
            incident_id = UUID(incident.id)

        agent_status.set_state("sentinel", incident_id, "running")
        await self._emit(incident_id, "sentinel", "sentinel_alert", anomaly)
        agent_status.set_state("sentinel", incident_id, "idle")

        # Fire and forget: the caller (REST endpoint) gets the incident_id
        # back immediately, the crew runs asynchronously and streams
        # progress over the WebSocket, matching the real-time UI contract.
        import asyncio

        asyncio.create_task(self._run_crew(incident_id, anomaly))
        return incident_id

    async def _run_crew(self, incident_id: UUID, anomaly: dict) -> None:
        crew = get_crew()
        try:
            await self._set_status(incident_id, IncidentStatus.investigating)
            agent_status.set_state("detective", incident_id, "running")
            finding = await crew["detective"].run(str(incident_id), anomaly)
            agent_status.set_state("detective", incident_id, "idle")
            await self._record_agent_event(incident_id, "detective", "detective_finding", finding)

            await self._set_status(incident_id, IncidentStatus.briefed)
            agent_status.set_state("producer", incident_id, "running")
            brief = await crew["producer"].run(str(incident_id), {**anomaly, **finding})
            agent_status.set_state("producer", incident_id, "idle")
            await self._record_agent_event(incident_id, "producer", "producer_brief", brief)
            await self._set_grafana_incident_id(incident_id, brief.get("grafana_incident_id"))

            # The playbook table (see playbooks.py) decides risk tier from the
            # breaching metric *before* the Responder runs, so low-risk actions
            # (e.g. scaling encoder capacity) skip the approval UI entirely and
            # go straight to Remediating, matching the state machine in
            # docs/low-level-design.md -- only high-risk actions block on a
            # human via request_human_approval inside crew["responder"].run().
            playbook = select_playbook(anomaly.get("metric_name"))
            if playbook["risk_level"] == "high":
                await self._set_status(incident_id, IncidentStatus.awaiting_approval)
                await self._emit(
                    incident_id,
                    "responder",
                    "responder_action_pending",
                    {
                        "grafana_incident_id": brief.get("grafana_incident_id"),
                        "action_type": playbook["action_type"],
                        "description": playbook["description"],
                    },
                )
                agent_status.set_state("responder", incident_id, "blocked")
            else:
                await self._set_status(incident_id, IncidentStatus.remediating)
                agent_status.set_state("responder", incident_id, "running")

            resolution = await crew["responder"].run(str(incident_id), {**anomaly, **brief})
            agent_status.set_state("responder", incident_id, "idle")
            await self._record_remediation(incident_id, resolution)
            executed = resolution.get("approval_status") in ("approved", "not_required")
            event_type = "responder_action_executed" if executed else "incident_resolved"
            await self._record_agent_event(incident_id, "responder", event_type, resolution)

            await self._set_status(
                incident_id, IncidentStatus.resolved if executed else IncidentStatus.skipped, resolved=executed
            )
            await self._emit(incident_id, "responder", "incident_resolved", resolution)

            agent_status.set_state("wrap", incident_id, "running")
            events = await self._events_for_wrap(incident_id)
            postmortem = await crew["wrap"].run(
                str(incident_id),
                {
                    "incident_id": str(incident_id),
                    "events": events,
                    "title": brief.get("title", ""),
                    "resolution": resolution,
                },
            )
            agent_status.set_state("wrap", incident_id, "idle")
            await self._record_postmortem(incident_id, postmortem)
            await self._set_status(incident_id, IncidentStatus.postmortem_ready)
            await self._emit(incident_id, "wrap", "postmortem_ready", postmortem)
        except Exception:
            logger.exception("Crew run failed for incident %s", incident_id)
            agent_status.clear_incident(incident_id)

    async def resolve_pending_approval(self, incident_id: UUID, approved: bool, actor: str) -> bool:
        ok = resolve_approval(incident_id, approved)
        if ok:
            logger.info("Incident %s approval resolved by %s: %s", incident_id, actor, approved)
        return ok

    # --- persistence + broadcast helpers ----------------------------------

    async def _set_status(self, incident_id: UUID, status: IncidentStatus, *, resolved: bool = False) -> None:
        async with session_scope() as db:
            incident = await db.get(Incident, str(incident_id))
            if incident is None:
                return
            incident.status = status.value
            if resolved:
                incident.resolved_at = datetime.utcnow()
            await db.commit()

    async def _set_grafana_incident_id(self, incident_id: UUID, grafana_incident_id: str | None) -> None:
        if not grafana_incident_id:
            return
        async with session_scope() as db:
            incident = await db.get(Incident, str(incident_id))
            if incident is None:
                return
            incident.grafana_incident_id = grafana_incident_id
            await db.commit()

    async def _record_agent_event(self, incident_id: UUID, agent: str, event_type: str, payload: dict) -> None:
        async with session_scope() as db:
            db.add(
                AgentEventRow(
                    incident_id=str(incident_id),
                    agent_name=agent,
                    event_type=event_type,
                    payload_json=payload,
                )
            )
            await db.commit()
        await self._emit(incident_id, agent, event_type, payload)  # type: ignore[arg-type]

    async def _record_remediation(self, incident_id: UUID, resolution: dict) -> None:
        async with session_scope() as db:
            executed_at = resolution.get("executed_at")
            db.add(
                RemediationActionRow(
                    incident_id=str(incident_id),
                    action_type=resolution.get("action_type", "unknown"),
                    risk_level=resolution.get("risk_level", "low"),
                    approval_status=resolution.get("approval_status", "not_required"),
                    approved_by=resolution.get("approved_by"),
                    executed_at=datetime.fromisoformat(executed_at) if executed_at else None,
                )
            )
            await db.commit()

    async def _record_postmortem(self, incident_id: UUID, postmortem: dict) -> None:
        async with session_scope() as db:
            db.add(
                PostmortemRow(
                    incident_id=str(incident_id),
                    summary_markdown=postmortem.get("summary_markdown", ""),
                    timeline_json=postmortem.get("timeline", []),
                )
            )
            await db.commit()

    async def _events_for_wrap(self, incident_id: UUID) -> list[dict]:
        async with session_scope() as db:
            rows = (
                await db.execute(
                    select(AgentEventRow)
                    .where(AgentEventRow.incident_id == str(incident_id))
                    .order_by(AgentEventRow.created_at)
                )
            ).scalars()
            return [
                {"agent_name": r.agent_name, "event_type": r.event_type, "created_at": r.created_at.isoformat()}
                for r in rows
            ]

    async def _emit(self, incident_id: UUID, agent: str, event_type: str, payload: dict) -> None:
        envelope = AgentEventEnvelope(type=event_type, incident_id=incident_id, agent=agent, payload=payload)
        await manager.broadcast(envelope.model_dump_json())


orchestrator = Orchestrator()
