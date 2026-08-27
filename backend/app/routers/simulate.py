from fastapi import APIRouter, Depends, HTTPException

from app.auth import CurrentUser, record_audit, require_role
from app.config import get_settings
from app.models.schemas import ChaosRequest, ChaosResponse, InjectAnomalyRequest, InjectAnomalyResponse
from app.orchestrator import orchestrator
from app.simulate import otel_pipeline
from app.simulate.synthetic_pipeline import build_anomaly

router = APIRouter()


@router.post("/inject-anomaly", response_model=InjectAnomalyResponse)
async def inject_anomaly(
    request: InjectAnomalyRequest, current: CurrentUser = Depends(require_role("operator"))
) -> InjectAnomalyResponse:
    """Demo endpoint: skips telemetry and hands the crew an already-detected
    anomaly directly, for driving the control room UI without waiting on the
    synthetic pipeline or a real Sentinel poll cycle. See /chaos below for
    the version that goes through real telemetry instead."""
    settings = get_settings()
    if not settings.demo_mode:
        raise HTTPException(403, "DEMO_MODE is disabled")

    anomaly = build_anomaly(request.metric_name, request.observed_value, request.threshold, request.region)
    incident_id = await orchestrator.start_incident(anomaly, workspace_id=current.workspace_id)
    await record_audit(
        current.email, "inject_anomaly", "incident", str(incident_id), {"metric_name": request.metric_name}
    )
    return InjectAnomalyResponse(incident_id=incident_id)


@router.post("/chaos", response_model=ChaosResponse)
async def trigger_chaos(
    request: ChaosRequest, current: CurrentUser = Depends(require_role("operator"))
) -> ChaosResponse:
    """Spike one metric/region combination in the synthetic live pipeline
    (app/simulate/otel_pipeline.py) for real -- the pipeline emits the
    breach as actual OpenTelemetry data, which a real Sentinel agent
    polling a real Grafana stack (services/sentinel_loop.py) would then
    discover and act on, the same way it would for a genuine incident.
    Unlike /inject-anomaly, this does not itself start an incident."""
    settings = get_settings()
    if not settings.demo_mode:
        raise HTTPException(403, "DEMO_MODE is disabled")

    try:
        otel_pipeline.trigger_chaos(request.metric_name, request.region, request.duration_seconds)
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc
    await record_audit(
        current.email, "trigger_chaos", "telemetry", None, {"metric_name": request.metric_name, "region": request.region}
    )
    return ChaosResponse(metric_name=request.metric_name, region=request.region, duration_seconds=request.duration_seconds)
