"""Drives one incident through the Sentinel(already-detected) -> Detective ->
Producer -> Responder -> Wrap loop, persisting every step to Firestore
(app/services/incident_store.py) and streaming it to the control room UI
over WebSocket.

See docs/low-level-design.md for the state machine and sequence diagram
this module implements, and docs/agents.md for the underlying agent crew.
"""

import asyncio
import logging
from uuid import UUID

from app.adk_agents.approval import has_pending_approval, resolve_approval, take_resolved_by
from app.adk_agents.crew import get_crew
from app.adk_agents.playbooks import select_playbook
from app.config import get_settings
from app.models.db import DEFAULT_WORKSPACE_ID
from app.models.schemas import AgentEventEnvelope, IncidentStatus
from app.services import agent_status, incident_store, notifications
from app.ws.manager import manager

logger = logging.getLogger(__name__)


class Orchestrator:
    async def start_incident(self, anomaly: dict, workspace_id: str = DEFAULT_WORKSPACE_ID) -> UUID:
        """Persist the Sentinel-detected anomaly as a new incident and kick off the crew."""
        title = f"SLO breach: {anomaly['metric_name']} in {anomaly['region']}"
        incident_id_str = await incident_store.create_incident(
            title=title, status=IncidentStatus.anomaly_detected.value, workspace_id=workspace_id, anomaly=anomaly
        )
        incident_id = UUID(incident_id_str)

        agent_status.set_state("sentinel", incident_id, "running")
        await self._emit(incident_id, "sentinel", "sentinel_alert", anomaly)
        agent_status.set_state("sentinel", incident_id, "idle")

        # Fire and forget: the caller (REST endpoint) gets the incident_id
        # back immediately, the crew runs asynchronously and streams
        # progress over the WebSocket, matching the real-time UI contract.
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
            await self._record_token_usage(incident_id, "detective", crew["detective"])

            await self._set_status(incident_id, IncidentStatus.briefed)
            agent_status.set_state("producer", incident_id, "running")
            brief = await crew["producer"].run(str(incident_id), {**anomaly, **finding})
            agent_status.set_state("producer", incident_id, "idle")
            await self._record_agent_event(incident_id, "producer", "producer_brief", brief)
            await self._record_token_usage(incident_id, "producer", crew["producer"])
            await incident_store.set_grafana_incident_id(str(incident_id), brief.get("grafana_incident_id"))

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
                await notifications.notify(
                    "approval_needed",
                    str(incident_id),
                    brief.get("title", "Incident awaiting approval"),
                    f"Responder proposes {playbook['action_type']}: {playbook['description']}",
                )
                asyncio.create_task(self._escalate_if_unresolved(incident_id, brief.get("title", "")))
            else:
                await self._set_status(incident_id, IncidentStatus.remediating)
                agent_status.set_state("responder", incident_id, "running")

            resolution = await crew["responder"].run(str(incident_id), {**anomaly, **brief})
            agent_status.set_state("responder", incident_id, "idle")
            await self._record_remediation(incident_id, resolution)
            await self._record_token_usage(incident_id, "responder", crew["responder"])
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
            await self._record_token_usage(incident_id, "wrap", crew["wrap"])
            await incident_store.record_postmortem(str(incident_id), postmortem)
            await self._set_status(incident_id, IncidentStatus.postmortem_ready)
            await self._emit(incident_id, "wrap", "postmortem_ready", postmortem)
            await notifications.notify(
                "resolved",
                str(incident_id),
                brief.get("title", "Incident resolved"),
                "Postmortem ready." if executed else "Remediation was rejected; left for manual follow-up.",
            )
        except Exception:
            logger.exception("Crew run failed for incident %s", incident_id)
            agent_status.clear_incident(incident_id)

    async def _escalate_if_unresolved(self, incident_id: UUID, title: str) -> None:
        """If a high-risk action is still awaiting approval after
        ESCALATION_TIMEOUT_SECONDS, send a reminder notification -- the
        "smarter crew" escalation-policy angle: the crew doesn't just wait
        forever for a human, it re-pages when one hasn't shown up."""
        settings = get_settings()
        await asyncio.sleep(settings.escalation_timeout_seconds)
        if has_pending_approval(incident_id):
            await notifications.notify(
                "escalation",
                str(incident_id),
                title or "Incident still awaiting approval",
                f"No response after {settings.escalation_timeout_seconds:.0f}s -- escalating.",
            )

    async def resolve_pending_approval(self, incident_id: UUID, approved: bool, actor: str) -> bool:
        ok = resolve_approval(incident_id, approved, actor=actor)
        if ok:
            logger.info("Incident %s approval resolved by %s: %s", incident_id, actor, approved)
        return ok

    # --- persistence + broadcast helpers ----------------------------------

    async def _set_status(self, incident_id: UUID, status: IncidentStatus, *, resolved: bool = False) -> None:
        await incident_store.set_status(str(incident_id), status.value, resolved=resolved)

    async def _record_agent_event(self, incident_id: UUID, agent: str, event_type: str, payload: dict) -> None:
        await incident_store.record_agent_event(str(incident_id), agent, event_type, payload)
        await self._emit(incident_id, agent, event_type, payload)  # type: ignore[arg-type]

    async def _record_remediation(self, incident_id: UUID, resolution: dict) -> None:
        # The agent's own structured output has an approved_by field, but an
        # LLM has no way to know who actually clicked approve -- the real,
        # authenticated actor (captured by resolve_pending_approval) is the
        # source of truth whenever one exists.
        real_approver = take_resolved_by(incident_id)
        approved_by = real_approver or resolution.get("approved_by")
        await incident_store.record_remediation(str(incident_id), resolution, approved_by)

    async def _record_token_usage(self, incident_id: UUID, agent_name: str, invoker: object) -> None:
        """No-op for the mock crew's invokers, which never set last_usage
        since they never call an LLM -- see runner.AgentInvoker."""
        usage = getattr(invoker, "last_usage", None)
        if not usage:
            return
        await incident_store.record_token_usage(
            str(incident_id), agent_name, usage.get("input_tokens", 0), usage.get("output_tokens", 0)
        )

    async def _events_for_wrap(self, incident_id: UUID) -> list[dict]:
        events = await incident_store.get_incident_events(str(incident_id))
        return [
            {"agent_name": e["agent_name"], "event_type": e["event_type"], "created_at": e["created_at"].isoformat()}
            for e in events
        ]

    async def _emit(self, incident_id: UUID, agent: str, event_type: str, payload: dict) -> None:
        envelope = AgentEventEnvelope(type=event_type, incident_id=incident_id, agent=agent, payload=payload)
        await manager.broadcast(envelope.model_dump_json())


orchestrator = Orchestrator()
