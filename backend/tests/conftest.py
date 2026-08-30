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
# Routes every google-cloud-firestore call (app/services/incident_store.py)
# at a local emulator instead of real GCP credentials -- standard
# google-cloud-firestore behavior, see app/firestore_db.py. The
# _firestore_emulator fixture below spawns the emulator this points at; set
# here, before any app.* import, so nothing can construct a Firestore client
# against real ADC first.
os.environ["FIRESTORE_EMULATOR_HOST"] = "127.0.0.1:8081"
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

import signal  # noqa: E402
import subprocess  # noqa: E402
import time  # noqa: E402
import urllib.error  # noqa: E402
import urllib.request  # noqa: E402
from pathlib import Path  # noqa: E402

import pytest_asyncio  # noqa: E402
from httpx import ASGITransport, AsyncClient  # noqa: E402

from app.auth import ensure_bootstrap_data  # noqa: E402
from app.db import init_db  # noqa: E402
from app.main import app  # noqa: E402

ADMIN_EMAIL = os.environ["ADMIN_EMAIL"]
ADMIN_PASSWORD = os.environ["ADMIN_PASSWORD"]

_BACKEND_DIR = Path(__file__).resolve().parent.parent
_FIRESTORE_HOST, _FIRESTORE_PORT = os.environ["FIRESTORE_EMULATOR_HOST"].split(":")


def _wait_for_firestore_emulator(timeout: float = 90.0) -> None:
    url = f"http://{_FIRESTORE_HOST}:{_FIRESTORE_PORT}/"
    deadline = time.monotonic() + timeout
    last_error: Exception | None = None
    while time.monotonic() < deadline:
        try:
            urllib.request.urlopen(url, timeout=1)  # noqa: S310
            return
        except urllib.error.URLError as exc:
            last_error = exc
            time.sleep(0.5)
    raise RuntimeError(f"Firestore emulator did not become ready at {url}: {last_error}")


@pytest_asyncio.fixture(scope="session", autouse=True)
async def _firestore_emulator():
    """Spawns the Firestore emulator (via `npx firebase-tools`, config in
    backend/firebase.json + backend/.firebaserc) for the whole test session.
    app/services/incident_store.py needs a real Firestore endpoint to talk
    to; FIRESTORE_EMULATOR_HOST (set above, before any app.* import) points
    every google-cloud-firestore call at it instead of real GCP. Requires
    Node (npx) and Java (for the emulator jar) on PATH -- see
    docs/setup-guide.md.
    """
    # start_new_session=True puts npx and everything it spawns (the `firebase`
    # node process, and in turn the java emulator jar) in their own process
    # group, so terminating just the npx PID on teardown would otherwise
    # leave the java emulator running as an orphan.
    process = subprocess.Popen(  # noqa: S603, S607
        ["npx", "--yes", "firebase-tools@latest", "emulators:start", "--only", "firestore"],
        cwd=_BACKEND_DIR,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        start_new_session=True,
    )
    try:
        _wait_for_firestore_emulator()
        yield
    finally:
        try:
            os.killpg(process.pid, signal.SIGTERM)
        except ProcessLookupError:
            pass
        try:
            process.wait(timeout=10)
        except subprocess.TimeoutExpired:
            try:
                os.killpg(process.pid, signal.SIGKILL)
            except ProcessLookupError:
                pass


@pytest_asyncio.fixture(scope="session", autouse=True)
async def _initialized_db(_firestore_emulator):
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
