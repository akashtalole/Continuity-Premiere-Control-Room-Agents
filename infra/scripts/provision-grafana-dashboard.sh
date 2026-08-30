#!/usr/bin/env bash
# Creates (or updates) the "premiere-slo-overview" Grafana dashboard that
# the control room UI's embedded panel (app/page.tsx) and the backend's
# panel-image render endpoint (app/routers/dashboards.py) both point at by
# UID. Nothing else in this repo creates this dashboard -- it was always an
# assumed prerequisite, not something the synthetic telemetry pipeline or
# any deploy script provisions automatically. Run this once per Grafana
# Cloud stack.
#
# Usage:
#   export GRAFANA_URL="https://<stack>.grafana.net"
#   export GRAFANA_SERVICE_ACCOUNT_TOKEN="<token, Editor role or higher>"
#   bash infra/scripts/provision-grafana-dashboard.sh
#
# For the panels to show real data (not "No data"), the synthetic telemetry
# pipeline needs to be exporting into this same stack first -- see
# "Real OpenTelemetry export" in this directory's README.md. Panel queries
# below use the raw OTel metric names (app/simulate/otel_pipeline.py); if
# your stack's OTLP-to-Prometheus naming normalizes them differently,
# check via Grafana Explore and adjust the `expr` fields this script sends.

set -euo pipefail
cd "$(dirname "${BASH_SOURCE[0]}")"
source ./lib.sh

require_command curl
require_command python3

[[ -n "${GRAFANA_URL:-}" ]] || die "GRAFANA_URL is required, e.g. https://<stack>.grafana.net"
[[ -n "${GRAFANA_SERVICE_ACCOUNT_TOKEN:-}" ]] || die "GRAFANA_SERVICE_ACCOUNT_TOKEN is required (Editor role or higher)."

GRAFANA_URL="${GRAFANA_URL%/}"

log "Looking up the default Prometheus datasource on $GRAFANA_URL"
DATASOURCE_UID="$(
  curl -sS -H "Authorization: Bearer $GRAFANA_SERVICE_ACCOUNT_TOKEN" "$GRAFANA_URL/api/datasources" | python3 -c "
import json, sys
datasources = json.load(sys.stdin)
if isinstance(datasources, dict) and datasources.get('message'):
    sys.exit(f\"Grafana API error: {datasources['message']}\")
prom = [d for d in datasources if d.get('type') == 'prometheus']
if not prom:
    sys.exit('No Prometheus datasource found on this stack -- Grafana Cloud normally provisions one (grafanacloud-<stack>-prom) automatically.')
chosen = next((d for d in prom if d.get('isDefault')), prom[0])
print(chosen['uid'])
"
)"
[[ -n "$DATASOURCE_UID" ]] || die "Could not resolve a Prometheus datasource UID."
log "Using datasource UID: $DATASOURCE_UID"

DASHBOARD_JSON="$(python3 - "$DATASOURCE_UID" <<'PYEOF'
import json
import sys

ds_uid = sys.argv[1]


def ts_panel(panel_id, title, expr, unit="short"):
    return {
        "id": panel_id,
        "title": title,
        "type": "timeseries",
        "gridPos": {"h": 8, "w": 12, "x": 12 * ((panel_id - 1) % 2), "y": 8 * ((panel_id - 1) // 2)},
        "datasource": {"type": "prometheus", "uid": ds_uid},
        "fieldConfig": {"defaults": {"unit": unit}, "overrides": []},
        "targets": [
            {
                "datasource": {"type": "prometheus", "uid": ds_uid},
                "expr": expr,
                "legendFormat": "{{region}}",
                "refId": "A",
            }
        ],
    }


# panel 1 is deliberately "Rebuffer ratio" -- that's the metric id the
# frontend's GrafanaPanelEmbed and dashboard-panel-image render both
# request (panelId=1), and the one every demo doc/script leads with.
panels = [
    ts_panel(1, "Rebuffer ratio by region", "rebuffer_ratio", "percentunit"),
    ts_panel(2, "Origin error rate by region", "origin_error_rate", "percentunit"),
    ts_panel(3, "Encoder queue depth by region", "encoder_queue_depth", "short"),
    ts_panel(4, "Playback failure rate by region", "playback_failure_rate", "percentunit"),
    ts_panel(5, "Cache hit ratio by region", "cache_hit_ratio", "percentunit"),
]

dashboard = {
    "uid": "premiere-slo-overview",
    "title": "Premiere Control Room -- SLO Overview",
    "tags": ["premiere-control-room"],
    "timezone": "browser",
    "schemaVersion": 39,
    "refresh": "30s",
    "time": {"from": "now-30m", "to": "now"},
    "panels": panels,
}

print(
    json.dumps(
        {
            "dashboard": dashboard,
            "overwrite": True,
            "message": "provisioned by infra/scripts/provision-grafana-dashboard.sh",
        }
    )
)
PYEOF
)"

log "Creating/updating dashboard 'premiere-slo-overview'"
RESPONSE="$(
  curl -sS -X POST "$GRAFANA_URL/api/dashboards/db" \
    -H "Authorization: Bearer $GRAFANA_SERVICE_ACCOUNT_TOKEN" \
    -H "Content-Type: application/json" \
    -d "$DASHBOARD_JSON"
)"

echo "$RESPONSE" | python3 -c "
import json, sys
r = json.load(sys.stdin)
if r.get('status') != 'success':
    sys.exit(f'Grafana rejected the dashboard: {r}')
print(f\"Dashboard ready: {r.get('url', '(no url returned)')}\")
"

log "Panel 1 (Rebuffer ratio by region) is what the control room UI's embedded panel pulls from."
log "If panels show 'No data', the synthetic pipeline isn't exporting to this stack yet -- see"
log "infra/scripts/README.md#real-opentelemetry-export."
