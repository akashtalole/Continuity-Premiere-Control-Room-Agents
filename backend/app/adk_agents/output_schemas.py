"""Structured output schemas for agents whose reply shape isn't already
covered by app.models.schemas (see docs/low-level-design.md)."""

from pydantic import BaseModel


class SentinelFinding(BaseModel):
    anomaly_detected: bool
    metric_name: str | None = None
    observed_value: float | None = None
    threshold: float | None = None
    region: str | None = None
    reasoning: str = ""
