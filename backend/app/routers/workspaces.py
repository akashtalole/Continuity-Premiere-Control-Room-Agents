from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select

from app.auth import CurrentUser, record_audit, require_role
from app.db import session_scope
from app.models.db import Workspace
from app.models.schemas import CreateWorkspaceRequest, WorkspaceSummary

router = APIRouter()


@router.get("", response_model=list[WorkspaceSummary])
async def list_workspaces() -> list[WorkspaceSummary]:
    """Unauthenticated, like GET /api/incidents -- just names/ids for the
    read-only workspace switcher. Which incidents/actions a signed-in user
    can actually touch is still gated by their own workspace_id everywhere
    else -- see routers/incidents.py, simulate.py."""
    async with session_scope() as db:
        rows = (await db.execute(select(Workspace).order_by(Workspace.created_at))).scalars()
        return [WorkspaceSummary(id=r.id, name=r.name, created_at=r.created_at) for r in rows]


@router.post("", response_model=WorkspaceSummary)
async def create_workspace(
    request: CreateWorkspaceRequest, current: CurrentUser = Depends(require_role("admin"))
) -> WorkspaceSummary:
    async with session_scope() as db:
        if await db.get(Workspace, request.id) is not None:
            raise HTTPException(409, "A workspace with that id already exists")
        workspace = Workspace(id=request.id, name=request.name)
        db.add(workspace)
        await db.commit()
        await db.refresh(workspace)

    await record_audit(current.email, "workspace_created", "workspace", workspace.id, {"name": request.name})
    return WorkspaceSummary(id=workspace.id, name=workspace.name, created_at=workspace.created_at)
