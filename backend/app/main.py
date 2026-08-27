import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware

from app.auth import ensure_bootstrap_data
from app.config import get_settings
from app.db import init_db
from app.routers import agents, analytics, audit, auth, dashboards, health, incidents, simulate, workspaces
from app.services import sentinel_loop
from app.simulate import otel_pipeline
from app.ws.manager import manager

logging.basicConfig(level=logging.INFO)


@asynccontextmanager
async def lifespan(app: FastAPI):
    await init_db()
    await ensure_bootstrap_data()
    otel_pipeline.start()
    sentinel_loop.start()
    yield
    await sentinel_loop.stop()
    await otel_pipeline.stop()


app = FastAPI(title="Premiere Control Room API", lifespan=lifespan)

settings = get_settings()
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origin_list,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(health.router)
app.include_router(incidents.router, prefix="/api/incidents", tags=["incidents"])
app.include_router(agents.router, prefix="/api/agents", tags=["agents"])
app.include_router(dashboards.router, prefix="/api/dashboards", tags=["dashboards"])
app.include_router(simulate.router, prefix="/api/simulate", tags=["simulate"])
app.include_router(analytics.router, prefix="/api/analytics", tags=["analytics"])
app.include_router(auth.router, prefix="/api/auth", tags=["auth"])
app.include_router(audit.router, prefix="/api/audit-log", tags=["audit"])
app.include_router(workspaces.router, prefix="/api/workspaces", tags=["workspaces"])


@app.websocket("/ws/control-room")
async def control_room_socket(ws: WebSocket) -> None:
    await manager.connect(ws)
    try:
        while True:
            await ws.receive_text()  # heartbeat / no-op from client
    except WebSocketDisconnect:
        manager.disconnect(ws)
