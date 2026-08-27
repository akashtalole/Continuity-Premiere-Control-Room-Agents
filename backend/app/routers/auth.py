from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select

from app.auth import (
    CurrentUser,
    create_access_token,
    get_current_user,
    hash_password,
    record_audit,
    require_role,
    verify_password,
)
from app.db import session_scope
from app.models.db import User
from app.models.schemas import CreateUserRequest, LoginRequest, LoginResponse, UserSummary

router = APIRouter()


@router.post("/login", response_model=LoginResponse)
async def login(request: LoginRequest) -> LoginResponse:
    async with session_scope() as db:
        user = (await db.execute(select(User).where(User.email == request.email))).scalar_one_or_none()

    if user is None or not user.active or not verify_password(request.password, user.password_hash):
        raise HTTPException(401, "Invalid email or password")

    await record_audit(user.email, "login", "user", user.id)
    return LoginResponse(
        access_token=create_access_token(user),
        email=user.email,
        role=user.role,  # type: ignore[arg-type]
        workspace_id=user.workspace_id,
    )


@router.get("/me", response_model=UserSummary)
async def me(current: CurrentUser = Depends(get_current_user)) -> UserSummary:
    async with session_scope() as db:
        user = await db.get(User, current.id)
        if user is None:
            raise HTTPException(404, "User not found")
        return UserSummary(
            id=UUID(user.id),
            email=user.email,
            role=user.role,  # type: ignore[arg-type]
            workspace_id=user.workspace_id,
            active=user.active,
            created_at=user.created_at,
        )


@router.get("/users", response_model=list[UserSummary])
async def list_users(current: CurrentUser = Depends(require_role("admin"))) -> list[UserSummary]:
    async with session_scope() as db:
        rows = (await db.execute(select(User).order_by(User.created_at))).scalars()
        return [
            UserSummary(
                id=UUID(r.id),
                email=r.email,
                role=r.role,  # type: ignore[arg-type]
                workspace_id=r.workspace_id,
                active=r.active,
                created_at=r.created_at,
            )
            for r in rows
        ]


@router.post("/users", response_model=UserSummary)
async def create_user(request: CreateUserRequest, current: CurrentUser = Depends(require_role("admin"))) -> UserSummary:
    async with session_scope() as db:
        existing = (await db.execute(select(User).where(User.email == request.email))).scalar_one_or_none()
        if existing is not None:
            raise HTTPException(409, "A user with that email already exists")
        user = User(
            email=request.email,
            password_hash=hash_password(request.password),
            role=request.role,
            workspace_id=request.workspace_id,
        )
        db.add(user)
        await db.commit()
        await db.refresh(user)

    await record_audit(current.email, "user_created", "user", user.id, {"role": request.role, "workspace_id": request.workspace_id})
    return UserSummary(
        id=UUID(user.id),
        email=user.email,
        role=user.role,  # type: ignore[arg-type]
        workspace_id=user.workspace_id,
        active=user.active,
        created_at=user.created_at,
    )


@router.post("/users/{user_id}/revoke", response_model=UserSummary)
async def revoke_user(user_id: UUID, current: CurrentUser = Depends(require_role("admin"))) -> UserSummary:
    async with session_scope() as db:
        user = await db.get(User, str(user_id))
        if user is None:
            raise HTTPException(404, "User not found")
        user.active = False
        await db.commit()
        await db.refresh(user)

    await record_audit(current.email, "user_revoked", "user", user.id)
    return UserSummary(
        id=UUID(user.id),
        email=user.email,
        role=user.role,  # type: ignore[arg-type]
        workspace_id=user.workspace_id,
        active=user.active,
        created_at=user.created_at,
    )
