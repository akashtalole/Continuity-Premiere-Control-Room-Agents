from uuid import UUID

from fastapi import APIRouter, Depends
from sqlalchemy import select

from app.auth import CurrentUser, require_role
from app.db import session_scope
from app.models.db import AuditLogRow
from app.models.schemas import AuditLogEntry

router = APIRouter()


@router.get("", response_model=list[AuditLogEntry])
async def list_audit_log(limit: int = 200, current: CurrentUser = Depends(require_role("operator"))) -> list[AuditLogEntry]:
    async with session_scope() as db:
        rows = (
            await db.execute(select(AuditLogRow).order_by(AuditLogRow.created_at.desc()).limit(min(limit, 1000)))
        ).scalars()
        return [
            AuditLogEntry(
                id=UUID(r.id),
                actor_email=r.actor_email,
                action=r.action,
                resource_type=r.resource_type,
                resource_id=r.resource_id,
                detail=r.detail_json,
                created_at=r.created_at,
            )
            for r in rows
        ]
