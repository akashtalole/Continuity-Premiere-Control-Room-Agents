"""End-to-end tests against the mock crew (no GOOGLE_API_KEY/GRAFANA_URL --
see conftest.py), driving the same REST surface the frontend uses. These
exercise the orchestrator's fire-and-forget asyncio.Task the same way the
manual curl/websocket smoke tests earlier in development did: poll the
incident's status over the API until it reaches the state we're waiting
for, since the crew run happens in the background."""

import asyncio


async def _wait_for_status(client, incident_id: str, targets: set[str], timeout: float = 5.0) -> dict:
    elapsed = 0.0
    data = {}
    while elapsed < timeout:
        resp = await client.get(f"/api/incidents/{incident_id}")
        data = resp.json()
        if data["status"] in targets:
            return data
        await asyncio.sleep(0.1)
        elapsed += 0.1
    raise AssertionError(f"incident {incident_id} did not reach {targets} within {timeout}s; last status={data.get('status')}")


async def test_high_risk_incident_blocks_on_approval_then_resolves(client):
    resp = await client.post(
        "/api/simulate/inject-anomaly",
        json={"metric_name": "rebuffer_ratio", "observed_value": 0.2, "threshold": 0.05, "region": "us-east-1"},
    )
    assert resp.status_code == 200
    incident_id = resp.json()["incident_id"]

    data = await _wait_for_status(client, incident_id, {"awaiting_approval"})
    assert data["status"] == "awaiting_approval"

    approve = await client.post(f"/api/incidents/{incident_id}/approve")
    assert approve.status_code == 200
    assert approve.json()["status"] == "approved"

    data = await _wait_for_status(client, incident_id, {"postmortem_ready"})
    executed = [e for e in data["events"] if e["event_type"] == "responder_action_executed"]
    assert executed, "expected a responder_action_executed event"
    assert executed[0]["payload"]["action_type"] == "cdn_regional_failover"
    assert executed[0]["payload"]["approval_status"] == "approved"

    postmortem = await client.get(f"/api/incidents/{incident_id}/postmortem")
    assert postmortem.status_code == 200
    assert "executed" in postmortem.json()["summary_markdown"].lower()


async def test_low_risk_incident_auto_executes_without_approval(client):
    resp = await client.post(
        "/api/simulate/inject-anomaly",
        json={"metric_name": "encoder_queue_depth", "observed_value": 80, "threshold": 50, "region": "us-west-2"},
    )
    incident_id = resp.json()["incident_id"]

    # Should never pass through awaiting_approval -- it goes straight to
    # remediating/resolved. Poll for the terminal state directly.
    data = await _wait_for_status(client, incident_id, {"postmortem_ready"})

    executed = [e for e in data["events"] if e["event_type"] == "responder_action_executed"]
    assert executed[0]["payload"]["action_type"] == "scale_encoder_capacity"
    assert executed[0]["payload"]["approval_status"] == "not_required"

    postmortem = await client.get(f"/api/incidents/{incident_id}/postmortem")
    assert "was executed" in postmortem.json()["summary_markdown"]


async def test_reject_marks_the_incident_skipped_but_still_writes_a_postmortem(client):
    resp = await client.post(
        "/api/simulate/inject-anomaly",
        json={"metric_name": "origin_error_rate", "observed_value": 0.1, "threshold": 0.02, "region": "eu-west-1"},
    )
    incident_id = resp.json()["incident_id"]

    await _wait_for_status(client, incident_id, {"awaiting_approval"})
    reject = await client.post(f"/api/incidents/{incident_id}/reject")
    assert reject.json()["status"] == "rejected"

    data = await _wait_for_status(client, incident_id, {"postmortem_ready"})
    resolved = [e for e in data["events"] if e["event_type"] == "incident_resolved"]
    assert resolved[0]["payload"]["approval_status"] == "rejected"
    assert resolved[0]["payload"]["executed_at"] is None


async def test_approving_an_incident_with_no_pending_approval_returns_404(client):
    resp = await client.post("/api/incidents/00000000-0000-0000-0000-000000000000/approve")
    assert resp.status_code == 404


async def test_concurrent_incidents_are_tracked_independently(client):
    r1 = await client.post(
        "/api/simulate/inject-anomaly",
        json={"metric_name": "rebuffer_ratio", "observed_value": 0.2, "threshold": 0.05, "region": "us-east-1"},
    )
    r2 = await client.post(
        "/api/simulate/inject-anomaly",
        json={"metric_name": "playback_failure_rate", "observed_value": 0.05, "threshold": 0.01, "region": "apac"},
    )
    incident_1, incident_2 = r1.json()["incident_id"], r2.json()["incident_id"]

    await _wait_for_status(client, incident_1, {"awaiting_approval"})
    await _wait_for_status(client, incident_2, {"awaiting_approval"})

    status_resp = await client.get("/api/agents/status")
    responder = next(a for a in status_resp.json() if a["name"] == "responder")
    assert incident_1 in responder["active_incidents"]
    assert incident_2 in responder["active_incidents"]
    assert responder["state"] == "blocked"

    await client.post(f"/api/incidents/{incident_1}/approve")
    await client.post(f"/api/incidents/{incident_2}/reject")

    await _wait_for_status(client, incident_1, {"postmortem_ready"})
    await _wait_for_status(client, incident_2, {"postmortem_ready"})


async def test_analytics_summary_reflects_incident_history(client):
    resp = await client.post(
        "/api/simulate/inject-anomaly",
        json={"metric_name": "cache_hit_ratio", "observed_value": 0.5, "threshold": 0.8, "region": "sa-east-1"},
    )
    incident_id = resp.json()["incident_id"]
    await _wait_for_status(client, incident_id, {"postmortem_ready"})

    summary = (await client.get("/api/analytics/summary")).json()
    assert summary["total_incidents"] >= 1
    assert summary["breaches_by_metric"].get("cache_hit_ratio", 0) >= 1
    assert summary["breaches_by_region"].get("sa-east-1", 0) >= 1
    assert summary["mttr_seconds"] is not None


async def test_health_reports_mock_agent_mode(client):
    resp = await client.get("/health")
    assert resp.status_code == 200
    assert resp.json() == {"status": "ok", "agent_mode": "mock"}
