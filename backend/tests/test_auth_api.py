"""Auth, audit log, and workspace coverage. See conftest.py for the
bootstrapped admin (ADMIN_EMAIL/ADMIN_PASSWORD) the `client` fixture logs
in as, and `anonymous_client` for the no-token path."""

from app.auth import ensure_bootstrap_data
from app.config import get_settings
from tests.conftest import ADMIN_EMAIL, ADMIN_PASSWORD


async def test_login_succeeds_with_correct_credentials(anonymous_client):
    resp = await anonymous_client.post("/api/auth/login", json={"email": ADMIN_EMAIL, "password": ADMIN_PASSWORD})
    assert resp.status_code == 200
    body = resp.json()
    assert body["email"] == ADMIN_EMAIL
    assert body["role"] == "admin"
    assert body["access_token"]


async def test_login_fails_with_wrong_password(anonymous_client):
    resp = await anonymous_client.post("/api/auth/login", json={"email": ADMIN_EMAIL, "password": "wrong"})
    assert resp.status_code == 401


async def test_ensure_bootstrap_data_resets_admin_password_on_every_call(anonymous_client):
    """ADMIN_PASSWORD is meant to be settable on every redeploy, not just the
    service's first-ever boot -- see the docstring on ensure_bootstrap_data.
    Uses a throwaway email so it doesn't disturb ADMIN_EMAIL's password for
    every other test in this session."""
    settings = get_settings()
    original_email, original_password = settings.admin_email, settings.admin_password
    throwaway_email = "bootstrap-reset-test@test.local"
    try:
        settings.admin_email = throwaway_email
        settings.admin_password = "first-password"
        await ensure_bootstrap_data()

        first_login = await anonymous_client.post(
            "/api/auth/login", json={"email": throwaway_email, "password": "first-password"}
        )
        assert first_login.status_code == 200

        settings.admin_password = "second-password"
        await ensure_bootstrap_data()

        stale_login = await anonymous_client.post(
            "/api/auth/login", json={"email": throwaway_email, "password": "first-password"}
        )
        assert stale_login.status_code == 401

        fresh_login = await anonymous_client.post(
            "/api/auth/login", json={"email": throwaway_email, "password": "second-password"}
        )
        assert fresh_login.status_code == 200
    finally:
        settings.admin_email, settings.admin_password = original_email, original_password


async def test_inject_anomaly_requires_auth(anonymous_client):
    resp = await anonymous_client.post(
        "/api/simulate/inject-anomaly",
        json={"metric_name": "rebuffer_ratio", "observed_value": 0.2, "threshold": 0.05, "region": "us-east-1"},
    )
    assert resp.status_code == 401


async def test_viewer_role_cannot_inject_anomaly(client, anonymous_client):
    create = await client.post(
        "/api/auth/users", json={"email": "viewer@test.local", "password": "viewer-pass", "role": "viewer"}
    )
    assert create.status_code == 200

    login = await anonymous_client.post("/api/auth/login", json={"email": "viewer@test.local", "password": "viewer-pass"})
    assert login.status_code == 200
    token = login.json()["access_token"]

    resp = await anonymous_client.post(
        "/api/simulate/inject-anomaly",
        json={"metric_name": "rebuffer_ratio", "observed_value": 0.2, "threshold": 0.05, "region": "us-east-1"},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 403


async def test_only_admin_can_create_users(anonymous_client):
    login = await anonymous_client.post("/api/auth/login", json={"email": ADMIN_EMAIL, "password": ADMIN_PASSWORD})
    admin_token = login.json()["access_token"]
    create_operator = await anonymous_client.post(
        "/api/auth/users",
        json={"email": "operator-for-role-test@test.local", "password": "op-pass", "role": "operator"},
        headers={"Authorization": f"Bearer {admin_token}"},
    )
    assert create_operator.status_code == 200

    operator_login = await anonymous_client.post(
        "/api/auth/login", json={"email": "operator-for-role-test@test.local", "password": "op-pass"}
    )
    operator_token = operator_login.json()["access_token"]
    forbidden = await anonymous_client.post(
        "/api/auth/users",
        json={"email": "someone-else@test.local", "password": "x", "role": "viewer"},
        headers={"Authorization": f"Bearer {operator_token}"},
    )
    assert forbidden.status_code == 403


async def test_approve_action_writes_an_audit_log_entry(client):
    resp = await client.post(
        "/api/simulate/inject-anomaly",
        json={"metric_name": "origin_error_rate", "observed_value": 0.1, "threshold": 0.02, "region": "eu-west-1"},
    )
    incident_id = resp.json()["incident_id"]

    for _ in range(50):
        detail = (await client.get(f"/api/incidents/{incident_id}")).json()
        if detail["status"] == "awaiting_approval":
            break
        import asyncio

        await asyncio.sleep(0.1)

    approve = await client.post(f"/api/incidents/{incident_id}/approve")
    assert approve.status_code == 200

    audit = await client.get("/api/audit-log")
    assert audit.status_code == 200
    entries = audit.json()
    matching = [e for e in entries if e["action"] == "approve_remediation" and e["resource_id"] == incident_id]
    assert matching, "expected an approve_remediation audit entry for this incident"
    assert matching[0]["actor_email"] == ADMIN_EMAIL


async def test_workspace_list_includes_default_and_admin_can_create_more(client):
    listed = await client.get("/api/workspaces")
    assert listed.status_code == 200
    ids = [w["id"] for w in listed.json()]
    assert "default" in ids

    created = await client.post("/api/workspaces", json={"id": "premiere-2", "name": "Premiere 2"})
    assert created.status_code == 200

    listed_again = await client.get("/api/workspaces")
    assert "premiere-2" in [w["id"] for w in listed_again.json()]


async def test_incident_detail_exposes_token_usage_field(client):
    resp = await client.post(
        "/api/simulate/inject-anomaly",
        json={"metric_name": "encoder_queue_depth", "observed_value": 80, "threshold": 50, "region": "us-west-2"},
    )
    incident_id = resp.json()["incident_id"]
    detail = (await client.get(f"/api/incidents/{incident_id}")).json()
    # Mock crew never calls a real model, so this is always empty -- the
    # point of this test is just that the field exists and round-trips.
    assert detail["token_usage"] == []
