from fastapi import APIRouter

from app.models.schemas import AgentStatus
from app.services import agent_status

router = APIRouter()


@router.get("/status", response_model=list[AgentStatus])
async def agents_status() -> list[AgentStatus]:
    snapshot = agent_status.snapshot()
    return [
        AgentStatus(name=name, state=info["state"], active_incidents=info["active_incidents"])
        for name, info in snapshot.items()
    ]
