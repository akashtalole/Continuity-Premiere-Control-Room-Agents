"""Human-in-the-loop approval gate for the Responder agent.

This is the concrete implementation of the hackathon's "Forced Function
Calling" pattern: the Responder's instruction (see instructions.py) forbids
calling any write tool for a high-risk action without first getting an
"approved" result from this tool, and this tool itself blocks on a real
asyncio.Future that only the FastAPI approve/reject endpoint can resolve.
The LLM cannot fabricate an approval -- it can only await one.
"""

import asyncio
import logging
from uuid import UUID

from google.adk.tools import FunctionTool

logger = logging.getLogger(__name__)

_pending: dict[str, asyncio.Future[bool]] = {}
# Populated by resolve_approval, consumed once by orchestrator._record_remediation.
# The agent's own structured output has an `approved_by` field too, but an LLM
# has no way to know who actually clicked approve -- this is the real,
# authenticated identity, and takes priority when persisting the record.
_resolved_by: dict[str, str] = {}


async def request_human_approval(incident_id: str, action_description: str, risk_level: str) -> str:
    """Block until a human approves or rejects this action via the control room UI.

    Call this before executing any write tool for an action classified as
    high risk. Do not call any Grafana write tool until this returns
    "approved".

    Args:
        incident_id: the incident this action belongs to.
        action_description: a plain-language description of the proposed
            remediation, shown to the human approver.
        risk_level: "low" or "high". Only "high" actually requires calling
            this tool, but it is safe to call for any risk level.

    Returns:
        "approved" or "rejected".
    """
    logger.info("Responder requesting human approval for incident %s: %s", incident_id, action_description)
    loop = asyncio.get_event_loop()
    future: asyncio.Future[bool] = loop.create_future()
    _pending[incident_id] = future
    try:
        approved = await future
    finally:
        _pending.pop(incident_id, None)
    return "approved" if approved else "rejected"


def resolve_approval(incident_id: UUID | str, approved: bool, actor: str | None = None) -> bool:
    """Called by POST /api/incidents/{id}/approve|reject. Returns False if nothing was pending."""
    future = _pending.get(str(incident_id))
    if future is None or future.done():
        return False
    if actor is not None:
        _resolved_by[str(incident_id)] = actor
    future.set_result(approved)
    return True


def take_resolved_by(incident_id: UUID | str) -> str | None:
    """Pops (one-shot) the real, authenticated actor who resolved this
    incident's pending approval, if any. See orchestrator._record_remediation."""
    return _resolved_by.pop(str(incident_id), None)


def has_pending_approval(incident_id: UUID | str) -> bool:
    future = _pending.get(str(incident_id))
    return future is not None and not future.done()


request_human_approval_tool = FunctionTool(func=request_human_approval)
