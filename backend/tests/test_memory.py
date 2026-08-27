"""Cross-incident memory: the mock crew's Detective calls the same
find_similar_incidents lookup the real Detective's tool uses (see
memory_tools.py), so a second breach of the same metric should reference
the first one's outcome and be more confident than a first-time breach."""

import asyncio


async def _wait_for_postmortem(client, incident_id: str, timeout: float = 5.0) -> dict:
    elapsed = 0.0
    while elapsed < timeout:
        resp = await client.get(f"/api/incidents/{incident_id}")
        data = resp.json()
        if data["status"] == "postmortem_ready":
            return data
        await asyncio.sleep(0.1)
        elapsed += 0.1
    raise AssertionError(f"incident {incident_id} never reached postmortem_ready")


async def test_second_breach_of_same_metric_references_precedent(client):
    first = await client.post(
        "/api/simulate/inject-anomaly",
        json={"metric_name": "cache_hit_ratio", "observed_value": 0.4, "threshold": 0.8, "region": "apac"},
    )
    first_id = first.json()["incident_id"]
    await _wait_for_postmortem(client, first_id)

    second = await client.post(
        "/api/simulate/inject-anomaly",
        json={"metric_name": "cache_hit_ratio", "observed_value": 0.35, "threshold": 0.8, "region": "apac"},
    )
    second_id = second.json()["incident_id"]
    detail = await _wait_for_postmortem(client, second_id)

    finding_event = next(e for e in detail["events"] if e["event_type"] == "detective_finding")
    assert "time '" in finding_event["payload"]["summary"]
    assert finding_event["payload"]["confidence"] > 0.82
