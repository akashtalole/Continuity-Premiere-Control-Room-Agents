"""Test isolation setup.

These env vars must be set *before* app.config / app.db are imported
anywhere (Settings() reads them at construction time, and app/db.py builds
its SQLAlchemy engine from get_settings() at module import time), so this
runs as plain module-level code -- not inside a fixture -- since pytest
imports conftest.py before collecting sibling test modules.
"""

import os
import tempfile

_tmp_db = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
_tmp_db.close()

os.environ["DATABASE_URL"] = f"sqlite+aiosqlite:///{_tmp_db.name}"
os.environ["DEMO_MODE"] = "true"
os.environ["GOOGLE_API_KEY"] = ""
os.environ["GRAFANA_URL"] = ""
os.environ["CORS_ORIGINS"] = "*"
# Background loops are irrelevant to these tests and would otherwise keep
# asyncio tasks alive across the whole session; tests call init_db()
# directly instead of going through the app's lifespan, so neither loop
# actually starts anyway -- these are set defensively in case that changes.
os.environ["SENTINEL_POLL_INTERVAL_SECONDS"] = "9999"
os.environ["SIMULATE_LIVE_PIPELINE"] = "false"
os.environ["ESCALATION_TIMEOUT_SECONDS"] = "9999"
# Deterministic bootstrap admin, so the `client` fixture below can log in
# without depending on ensure_bootstrap_data's random-password fallback.
os.environ["ADMIN_EMAIL"] = "admin@test.local"
os.environ["ADMIN_PASSWORD"] = "test-admin-password"
os.environ["JWT_SECRET"] = "test-jwt-secret-not-for-production"

import pytest_asyncio  # noqa: E402
from httpx import ASGITransport, AsyncClient  # noqa: E402

from app.auth import ensure_bootstrap_data  # noqa: E402
from app.db import init_db  # noqa: E402
from app.main import app  # noqa: E402

ADMIN_EMAIL = os.environ["ADMIN_EMAIL"]
ADMIN_PASSWORD = os.environ["ADMIN_PASSWORD"]


@pytest_asyncio.fixture(scope="session", autouse=True)
async def _initialized_db():
    await init_db()
    await ensure_bootstrap_data()
    yield
    try:
        os.unlink(_tmp_db.name)
    except OSError:
        pass


@pytest_asyncio.fixture
async def anonymous_client():
    """No Authorization header -- for testing the unauthenticated/negative
    paths directly. Most tests should use `client` below instead."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac


@pytest_asyncio.fixture
async def client(anonymous_client: AsyncClient):
    """Logged in as the bootstrapped admin by default, so every existing
    test that calls approve/reject/inject-anomaly keeps working unchanged
    now that those routes require an authenticated operator+ -- see
    test_auth_api.py for the auth behavior itself (401/403/roles)."""
    login = await anonymous_client.post("/api/auth/login", json={"email": ADMIN_EMAIL, "password": ADMIN_PASSWORD})
    assert login.status_code == 200, login.text
    token = login.json()["access_token"]
    anonymous_client.headers["Authorization"] = f"Bearer {token}"
    yield anonymous_client
