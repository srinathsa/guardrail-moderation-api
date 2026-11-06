"""POST /auth/login, GET /auth/me, and admin-only user management."""
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.auth import (
    CurrentUser,
    create_access_token,
    get_current_user,
    hash_password,
    require_roles,
    verify_password,
)
from app.db import crud
from app.db.database import get_db
from app.schemas import (
    CreateUserRequest,
    LoginRequest,
    LoginResponse,
    MeResponse,
    RegisterRequest,
    UserOut,
)

router = APIRouter(prefix="/auth", tags=["auth"])

VALID_ROLES = {"admin", "moderator", "client"}


@router.post("/register", response_model=LoginResponse)
async def register(payload: RegisterRequest, db: Session = Depends(get_db)):
    """
    Public self-signup for regular social-app users (always role="client").
    Staff accounts (admin/moderator) are created separately by an admin via
    POST /auth/users — this endpoint intentionally cannot create those.
    Returns a login token immediately so the new user is signed in right away.
    """
    username = payload.username.strip()
    if crud.get_user_by_username(db, username):
        raise HTTPException(409, "Username already taken")
    user = crud.create_user(
        db,
        username=username,
        password_hash=hash_password(payload.password),
        role="client",
    )
    token = create_access_token(username=user.username, role=user.role)
    return LoginResponse(access_token=token, username=user.username, role=user.role)


@router.post("/login", response_model=LoginResponse)
async def login(payload: LoginRequest, db: Session = Depends(get_db)):
    user = crud.get_user_by_username(db, payload.username)
    if not user or not verify_password(payload.password, user.password_hash):
        raise HTTPException(status_code=401, detail="Invalid username or password")
    token = create_access_token(username=user.username, role=user.role)
    return LoginResponse(access_token=token, username=user.username, role=user.role)


@router.get("/me", response_model=MeResponse)
async def me(user: CurrentUser = Depends(get_current_user)):
    return MeResponse(username=user.username, role=user.role)


@router.get("/users", response_model=list[UserOut])
async def list_users(
    db: Session = Depends(get_db),
    _user: CurrentUser = Depends(require_roles("admin")),
):
    return crud.list_users(db)


@router.post("/users", response_model=UserOut)
async def create_user(
    payload: CreateUserRequest,
    db: Session = Depends(get_db),
    _user: CurrentUser = Depends(require_roles("admin")),
):
    if payload.role not in VALID_ROLES:
        raise HTTPException(400, f"role must be one of {sorted(VALID_ROLES)}")
    if crud.get_user_by_username(db, payload.username):
        raise HTTPException(409, "Username already exists")
    new_user = crud.create_user(
        db,
        username=payload.username,
        password_hash=hash_password(payload.password),
        role=payload.role,
    )
    return new_user


@router.delete("/users/{user_id}")
async def delete_user(
    user_id: int,
    db: Session = Depends(get_db),
    user: CurrentUser = Depends(require_roles("admin")),
):
    if user.username and user_id == 1:
        raise HTTPException(400, "Cannot delete the primary bootstrap admin account")
    ok = crud.delete_user(db, user_id)
    if not ok:
        raise HTTPException(404, "User not found")
    return {"deleted": True, "id": user_id}
