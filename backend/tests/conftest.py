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

import pytest_asyncio  # noqa: E402
from httpx import ASGITransport, AsyncClient  # noqa: E402

from app.db import init_db  # noqa: E402
from app.main import app  # noqa: E402


@pytest_asyncio.fixture(scope="session", autouse=True)
async def _initialized_db():
    await init_db()
    yield
    try:
        os.unlink(_tmp_db.name)
    except OSError:
        pass


@pytest_asyncio.fixture
async def client():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac
