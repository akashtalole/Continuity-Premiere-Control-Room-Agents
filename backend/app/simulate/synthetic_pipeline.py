"""Demo-only synthetic anomaly injector.

Stands in for the "chaos script" milestone in docs/build-plan.md: a
reliable, on-cue way to trigger the full Sentinel->Wrap loop for a demo
recording without needing a real live streaming pipeline breaching real
Grafana SLOs. Only wired up when DEMO_MODE is true (see app/config.py).
"""

from datetime import datetime
from typing import Any


def build_anomaly(metric_name: str, observed_value: float, threshold: float, region: str) -> dict[str, Any]:
    return {
        "metric_name": metric_name,
        "observed_value": observed_value,
        "threshold": threshold,
        "region": region,
        "detected_at": datetime.utcnow().isoformat(),
    }
