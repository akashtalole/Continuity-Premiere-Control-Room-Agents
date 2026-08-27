"""Background Sentinel polling loop.

The rest of the system (mock crew, /api/simulate/inject-anomaly) treats
anomaly detection as an input handed to the orchestrator. This module is
the other half: when real Gemini + Grafana credentials are configured
(Settings.agents_configured), it periodically invokes the real Sentinel
agent against a small table of SLO thresholds and starts an incident
whenever it reports a breach -- the "poll interval" -> Sentinel ->
Detective chain from docs/low-level-design.md's sequence diagram, running
for real instead of only on demand.

Deliberately does nothing in mock mode: without a real Grafana stack there
are no real metrics to poll, so polling would just be re-running the mock
crew's deterministic detective on a timer, which adds noise without adding
signal. Use POST /api/simulate/inject-anomaly for demos instead.
"""

import asyncio
import json
import logging
from typing import Any

from sqlalchemy import select

from app.adk_agents.crew import get_crew
from app.config import get_settings
from app.db import session_scope
from app.models.db import Incident
from app.models.schemas import IncidentStatus

logger = logging.getLogger(__name__)

DEFAULT_SLO_THRESHOLDS: list[dict[str, Any]] = [
    {"metric_name": "rebuffer_ratio", "threshold": 0.05, "region": "us-east-1"},
    {"metric_name": "rebuffer_ratio", "threshold": 0.05, "region": "eu-west-1"},
    {"metric_name": "origin_error_rate", "threshold": 0.02, "region": "apac"},
    {"metric_name": "encoder_queue_depth", "threshold": 50, "region": "us-west-2"},
    {"metric_name": "playback_failure_rate", "threshold": 0.01, "region": "sa-east-1"},
]

_SETTLED_STATUSES = {IncidentStatus.resolved.value, IncidentStatus.postmortem_ready.value, IncidentStatus.skipped.value}

_task: asyncio.Task | None = None
_stop_event: asyncio.Event | None = None


def _slo_thresholds() -> list[dict[str, Any]]:
    raw = get_settings().sentinel_slo_thresholds_json
    if not raw:
        return DEFAULT_SLO_THRESHOLDS
    try:
        parsed = json.loads(raw)
        if isinstance(parsed, list):
            return parsed
    except json.JSONDecodeError:
        pass
    logger.warning("SENTINEL_SLO_THRESHOLDS_JSON is not a valid JSON list; using built-in defaults")
    return DEFAULT_SLO_THRESHOLDS


async def _has_open_incident(metric_name: str, region: str) -> bool:
    """Dedupe: don't open a second incident for a metric/region already mid-flight."""
    async with session_scope() as db:
        rows = (await db.execute(select(Incident.title, Incident.status))).all()
    needle = f"{metric_name} in {region}"
    return any(needle in title and status not in _SETTLED_STATUSES for title, status in rows)


async def _poll_once() -> None:
    from app.orchestrator import orchestrator  # local import: avoids a circular import at module load time

    sentinel = get_crew().get("sentinel")
    if sentinel is None:
        return

    for slo in _slo_thresholds():
        metric_name, threshold, region = slo["metric_name"], slo["threshold"], slo["region"]
        if await _has_open_incident(metric_name, region):
            continue
        try:
            finding = await sentinel.run(
                f"poll-{metric_name}-{region}",
                {"metric_name": metric_name, "threshold": threshold, "region": region},
            )
        except Exception:
            logger.exception("Sentinel poll failed for %s in %s", metric_name, region)
            continue

        if finding.get("anomaly_detected"):
            anomaly = {
                "metric_name": finding.get("metric_name") or metric_name,
                "observed_value": finding.get("observed_value") or threshold,
                "threshold": threshold,
                "region": finding.get("region") or region,
            }
            logger.info("Sentinel detected a breach via polling: %s", anomaly)
            await orchestrator.start_incident(anomaly)


async def _loop(interval_seconds: float) -> None:
    assert _stop_event is not None
    while not _stop_event.is_set():
        try:
            await _poll_once()
        except Exception:
            logger.exception("Sentinel polling loop iteration failed")
        try:
            await asyncio.wait_for(_stop_event.wait(), timeout=interval_seconds)
        except asyncio.TimeoutError:
            pass


def start() -> None:
    global _task, _stop_event
    settings = get_settings()
    if not settings.agents_configured:
        logger.info("Sentinel polling loop not started: GOOGLE_API_KEY/GRAFANA_URL are not configured")
        return
    if _task is not None:
        return
    _stop_event = asyncio.Event()
    _task = asyncio.create_task(_loop(settings.sentinel_poll_interval_seconds))
    logger.info("Sentinel polling loop started (interval=%ss)", settings.sentinel_poll_interval_seconds)


async def stop() -> None:
    global _task, _stop_event
    if _stop_event is not None:
        _stop_event.set()
    if _task is not None:
        await _task
    _task = None
    _stop_event = None
