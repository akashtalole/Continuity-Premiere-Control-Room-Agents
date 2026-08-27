"""Synthetic live streaming pipeline.

Stands in for the real CDN/encoder/origin stack (the "Live streaming
pipeline (synthetic)" box in docs/architecture.md and milestone 1,
"Telemetry stub", in docs/build-plan.md): it emits real OpenTelemetry
metrics, logs, and traces for five SLO metrics across five regions,
exported over OTLP when `OTEL_EXPORTER_OTLP_ENDPOINT` is set (point it at
Grafana Cloud's OTLP gateway, or a local otel-collector), and falling back
to the console exporters otherwise -- so `uvicorn app.main:app` alone shows
real telemetry values in the terminal with zero external dependencies.

This is deliberately independent of the mock/real agent crew split
(app/adk_agents/crew.py): it runs whenever `SIMULATE_LIVE_PIPELINE` is
true (the default), so that once a real Sentinel agent is polling a real
Grafana stack (see services/sentinel_loop.py), there is actual
PromQL-queryable data for it to find a breach in -- not just a demo
endpoint that skips straight to "here's a pre-made incident."

Use POST /api/simulate/chaos to spike one metric/region combination on
demand: the "chaos script" from docs/build-plan.md's milestone 7, for
reliably triggering a demo-able failure on cue.
"""

import asyncio
import logging
import random
import time
from dataclasses import dataclass, field

from opentelemetry import metrics, trace
from opentelemetry._logs import set_logger_provider
from opentelemetry.exporter.otlp.proto.http._log_exporter import OTLPLogExporter
from opentelemetry.exporter.otlp.proto.http.metric_exporter import OTLPMetricExporter
from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter
from opentelemetry.metrics import CallbackOptions, Observation
from opentelemetry.sdk._logs import LoggerProvider, LoggingHandler
from opentelemetry.sdk._logs.export import BatchLogRecordProcessor, ConsoleLogExporter
from opentelemetry.sdk.metrics import MeterProvider
from opentelemetry.sdk.metrics.export import ConsoleMetricExporter, PeriodicExportingMetricReader
from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor, ConsoleSpanExporter
from opentelemetry.trace import Status, StatusCode

from app.config import get_settings

logger = logging.getLogger(__name__)

REGIONS = ["us-east-1", "us-west-2", "eu-west-1", "apac", "sa-east-1"]

# metric_name -> (baseline, noise_stddev). All five map onto the playbook
# table in app/adk_agents/playbooks.py, so a spike here is exactly the kind
# of breach the Responder already has a remediation playbook for.
METRIC_BASELINES: dict[str, tuple[float, float]] = {
    "rebuffer_ratio": (0.01, 0.004),
    "origin_error_rate": (0.002, 0.001),
    "encoder_queue_depth": (5.0, 2.0),
    "playback_failure_rate": (0.001, 0.0005),
    "cache_hit_ratio": (0.94, 0.01),  # higher is healthier; chaos spikes this one *down*
}


@dataclass
class _PipelineState:
    values: dict[tuple[str, str], float] = field(default_factory=dict)
    spike_expiry: dict[tuple[str, str], float] = field(default_factory=dict)  # monotonic() deadline


_state = _PipelineState()


def _reset_state() -> None:
    _state.values = {(metric, region): baseline for metric, (baseline, _) in METRIC_BASELINES.items() for region in REGIONS}
    _state.spike_expiry.clear()


_reset_state()


def trigger_chaos(metric_name: str, region: str, duration_seconds: float = 45.0) -> None:
    """Spike one metric/region combination for a while -- see module docstring."""
    if (metric_name, region) not in _state.values:
        raise ValueError(f"unknown metric/region combination: {metric_name}/{region}")
    _state.spike_expiry[(metric_name, region)] = time.monotonic() + duration_seconds
    logger.info("Chaos triggered: %s in %s spiking for %.0fs", metric_name, region, duration_seconds)


def current_value(metric_name: str, region: str) -> float:
    return _state.values[(metric_name, region)]


def _tick() -> None:
    now = time.monotonic()
    for metric, (baseline, noise) in METRIC_BASELINES.items():
        for region in REGIONS:
            key = (metric, region)
            expiry = _state.spike_expiry.get(key)
            if expiry is not None and now < expiry:
                value = baseline * 0.3 if metric == "cache_hit_ratio" else baseline * 6.0
            else:
                _state.spike_expiry.pop(key, None)
                value = baseline + random.gauss(0, noise)
            _state.values[key] = max(0.0, value)


def _make_gauge_callback(metric_name: str):
    def callback(_options: CallbackOptions):
        for region in REGIONS:
            yield Observation(_state.values[(metric_name, region)], {"region": region})

    return callback


_meter_provider: MeterProvider | None = None
_tracer_provider: TracerProvider | None = None
_logger_provider: LoggerProvider | None = None
_tick_task: asyncio.Task | None = None
_stop_event: asyncio.Event | None = None


def _build_resource() -> Resource:
    return Resource.create(
        {"service.name": "premiere-control-room-live-pipeline", "service.namespace": "premiere-control-room"}
    )


def _configure_providers() -> None:
    global _meter_provider, _tracer_provider, _logger_provider
    settings = get_settings()
    resource = _build_resource()
    otlp_configured = bool(settings.otel_exporter_otlp_endpoint)

    metric_exporter = OTLPMetricExporter() if otlp_configured else ConsoleMetricExporter()
    reader = PeriodicExportingMetricReader(
        metric_exporter, export_interval_millis=int(settings.otel_export_interval_seconds * 1000)
    )
    _meter_provider = MeterProvider(resource=resource, metric_readers=[reader])
    metrics.set_meter_provider(_meter_provider)
    meter = _meter_provider.get_meter("premiere-control-room.live-pipeline")
    for metric_name in METRIC_BASELINES:
        meter.create_observable_gauge(
            name=metric_name,
            callbacks=[_make_gauge_callback(metric_name)],
            description=f"Synthetic {metric_name.replace('_', ' ')} for the premiere broadcast",
        )

    span_exporter = OTLPSpanExporter() if otlp_configured else ConsoleSpanExporter()
    _tracer_provider = TracerProvider(resource=resource)
    _tracer_provider.add_span_processor(BatchSpanProcessor(span_exporter))
    trace.set_tracer_provider(_tracer_provider)

    log_exporter = OTLPLogExporter() if otlp_configured else ConsoleLogExporter()
    _logger_provider = LoggerProvider(resource=resource)
    _logger_provider.add_log_record_processor(BatchLogRecordProcessor(log_exporter))
    set_logger_provider(_logger_provider)
    logging.getLogger("premiere-control-room.live-pipeline").addHandler(
        LoggingHandler(level=logging.INFO, logger_provider=_logger_provider)
    )


async def _loop(interval_seconds: float) -> None:
    assert _stop_event is not None
    tracer = trace.get_tracer("premiere-control-room.live-pipeline")
    pipeline_logger = logging.getLogger("premiere-control-room.live-pipeline")

    while not _stop_event.is_set():
        _tick()
        for region in REGIONS:
            with tracer.start_as_current_span("process_playback_request") as span:
                span.set_attribute("region", region)
                for metric_name in METRIC_BASELINES:
                    span.set_attribute(metric_name, _state.values[(metric_name, region)])

                baseline, _ = METRIC_BASELINES["rebuffer_ratio"]
                rebuffer = _state.values[("rebuffer_ratio", region)]
                if rebuffer > baseline * 3:
                    span.set_status(Status(StatusCode.ERROR, "elevated rebuffering"))
                    pipeline_logger.warning("Elevated rebuffer_ratio=%.4f in %s", rebuffer, region)
        try:
            await asyncio.wait_for(_stop_event.wait(), timeout=interval_seconds)
        except asyncio.TimeoutError:
            pass


def start() -> None:
    global _tick_task, _stop_event
    settings = get_settings()
    if not settings.simulate_live_pipeline:
        logger.info("Synthetic live pipeline disabled (SIMULATE_LIVE_PIPELINE=false)")
        return
    if _tick_task is not None:
        return
    _reset_state()
    _configure_providers()
    _stop_event = asyncio.Event()
    _tick_task = asyncio.create_task(_loop(settings.otel_tick_interval_seconds))
    mode = "OTLP export" if settings.otel_exporter_otlp_endpoint else "console export"
    logger.info("Synthetic live pipeline started (%s)", mode)


async def stop() -> None:
    global _tick_task, _stop_event
    if _stop_event is not None:
        _stop_event.set()
    if _tick_task is not None:
        await _tick_task
    _tick_task = None
    _stop_event = None
    for provider in (_tracer_provider, _meter_provider, _logger_provider):
        if provider is not None:
            provider.shutdown()
