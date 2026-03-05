import re
import secrets
import uuid

import httpx
from fastapi import APIRouter, Depends, Header, HTTPException, Request, status
from pydantic import BaseModel, EmailStr, field_validator
from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.database import get_db
from app.models.user import User
from app.rate_limit import limiter
from app.services.audit import log_event
from app.utils.security import (
    create_access_token,
    create_mfa_pending_token,
    create_refresh_token,
    decode_token,
    hash_password,
    verify_password,
)

router = APIRouter()


class RegisterRequest(BaseModel):
    email: EmailStr
    password: str

    @field_validator("password")
    @classmethod
    def validate_password(cls, v: str) -> str:
        if len(v) < 8:
            raise ValueError("Password must be at least 8 characters")
        if not re.search(r"[A-Z]", v):
            raise ValueError("Password must contain at least one uppercase letter")
        if not re.search(r"[a-z]", v):
            raise ValueError("Password must contain at least one lowercase letter")
        if not re.search(r"\d", v):
            raise ValueError("Password must contain at least one number")
        if not re.search(r"[^A-Za-z0-9]", v):
            raise ValueError("Password must contain at least one special character")
        return v


class LoginRequest(BaseModel):
    email: EmailStr
    password: str


class TokenResponse(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"


class RefreshRequest(BaseModel):
    refresh_token: str


class UserResponse(BaseModel):
    id: uuid.UUID
    email: str
    is_admin: bool = False

    model_config = {"from_attributes": True}


async def get_current_user(
    authorization: str = Header(""),
    db: AsyncSession = Depends(get_db),
) -> User:
    if not authorization.startswith("Bearer "):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Missing authorization header")
    token = authorization[7:]

    payload = decode_token(token)
    if not payload or payload.get("type") != "access":
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token")
    user_id = payload.get("sub")
    if not user_id:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token")
    result = await db.execute(select(User).where(User.id == uuid.UUID(user_id)))
    user = result.scalar_one_or_none()
    if not user:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="User not found")
    return user


@router.post("/register", response_model=TokenResponse, status_code=status.HTTP_201_CREATED)
@limiter.limit("5/minute")
async def register(request: Request, body: RegisterRequest, db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(User).where(User.email == body.email))
    if result.scalar_one_or_none():
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Email already registered")

    user = User(email=body.email, password_hash=hash_password(body.password))
    db.add(user)
    await db.commit()
    await db.refresh(user)

    await log_event(db, "REGISTER", request, user_id=user.id, details={"email": body.email})

    access_token = create_access_token({"sub": str(user.id)})
    refresh_token = create_refresh_token({"sub": str(user.id)})
    return TokenResponse(access_token=access_token, refresh_token=refresh_token)


@router.post("/login")
@limiter.limit("10/minute")
async def login(request: Request, body: LoginRequest, db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(User).where(User.email == body.email))
    user = result.scalar_one_or_none()
    if not user or not user.password_hash or not verify_password(body.password, user.password_hash):
        await log_event(db, "LOGIN_FAILED", request, user_id=user.id if user else None, details={"email": body.email})
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid email or password")

    if user.mfa_enabled:
        mfa_token = create_mfa_pending_token({"sub": str(user.id)})
        await log_event(db, "LOGIN_MFA_PENDING", request, user_id=user.id)
        return {"mfa_required": True, "mfa_token": mfa_token, "token_type": "bearer"}

    await log_event(db, "LOGIN_SUCCESS", request, user_id=user.id)
    access_token = create_access_token({"sub": str(user.id)})
    refresh_token = create_refresh_token({"sub": str(user.id)})
    return {"access_token": access_token, "refresh_token": refresh_token, "token_type": "bearer", "mfa_required": False}


@router.post("/refresh", response_model=TokenResponse)
@limiter.limit("30/minute")
async def refresh(request: Request, body: RefreshRequest, db: AsyncSession = Depends(get_db)):
    payload = decode_token(body.refresh_token)
    if not payload or payload.get("type") != "refresh":
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid refresh token")

    user_id = payload.get("sub")
    result = await db.execute(select(User).where(User.id == uuid.UUID(user_id)))
    user = result.scalar_one_or_none()
    if not user:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="User not found")

    access_token = create_access_token({"sub": str(user.id)})
    refresh_token = create_refresh_token({"sub": str(user.id)})
    return TokenResponse(access_token=access_token, refresh_token=refresh_token)


@router.post("/demo", response_model=TokenResponse)
@limiter.limit("5/minute")
async def demo_login(request: Request, db: AsyncSession = Depends(get_db)):
    from app.services.demo_seed import seed_demo_data

    user = await seed_demo_data(db)
    access_token = create_access_token({"sub": str(user.id)})
    refresh_token = create_refresh_token({"sub": str(user.id)})
    return TokenResponse(access_token=access_token, refresh_token=refresh_token)


@router.get("/me", response_model=UserResponse)
async def get_me(current_user: User = Depends(get_current_user)):
    is_admin = current_user.email.lower() in settings.admin_emails_set
    return UserResponse(id=current_user.id, email=current_user.email, is_admin=is_admin)


# ── GitHub OAuth ─────────────────────────────────────────────────


class GitHubCallbackRequest(BaseModel):
    code: str


@router.get("/github/authorize")
@limiter.limit("10/minute")
async def github_authorize(request: Request):
    if not settings.github_client_id:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="GitHub OAuth not configured")
    state = secrets.token_urlsafe(32)
    redirect_uri = f"{settings.frontend_url}/auth/github/callback"
    url = (
        f"https://github.com/login/oauth/authorize"
        f"?client_id={settings.github_client_id}"
        f"&redirect_uri={redirect_uri}"
        f"&scope=user:email"
        f"&state={state}"
    )
    return {"url": url, "state": state}


@router.post("/github/callback")
@limiter.limit("10/minute")
async def github_callback(request: Request, body: GitHubCallbackRequest, db: AsyncSession = Depends(get_db)):
    if not settings.github_client_id or not settings.github_client_secret:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="GitHub OAuth not configured")

    # 1. Exchange code for access token
    async with httpx.AsyncClient() as client:
        token_resp = await client.post(
            "https://github.com/login/oauth/access_token",
            json={
                "client_id": settings.github_client_id,
                "client_secret": settings.github_client_secret,
                "code": body.code,
            },
            headers={"Accept": "application/json"},
        )
        token_data = token_resp.json()

    gh_access_token = token_data.get("access_token")
    if not gh_access_token:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Failed to get GitHub access token")

    # 2. Fetch GitHub user profile
    async with httpx.AsyncClient() as client:
        user_resp = await client.get(
            "https://api.github.com/user",
            headers={"Authorization": f"Bearer {gh_access_token}", "Accept": "application/json"},
        )
        gh_user = user_resp.json()

    github_id = str(gh_user.get("id", ""))
    if not github_id:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Failed to get GitHub user info")

    # 3. Fetch primary verified email
    gh_email = gh_user.get("email")
    if not gh_email:
        async with httpx.AsyncClient() as client:
            emails_resp = await client.get(
                "https://api.github.com/user/emails",
                headers={"Authorization": f"Bearer {gh_access_token}", "Accept": "application/json"},
            )
            emails = emails_resp.json()
        for e in emails:
            if e.get("primary") and e.get("verified"):
                gh_email = e["email"]
                break
        if not gh_email and emails:
            gh_email = emails[0].get("email")

    if not gh_email:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="No email associated with GitHub account")

    # 4. Find or create user
    result = await db.execute(
        select(User).where(or_(User.github_id == github_id, User.email == gh_email))
    )
    user = result.scalar_one_or_none()

    if user:
        # Link GitHub if not already linked
        if not user.github_id:
            user.github_id = github_id
            await db.commit()
    else:
        # Create new user (OAuth-only, no password)
        user = User(email=gh_email, github_id=github_id, password_hash=None)
        db.add(user)
        await db.commit()
        await db.refresh(user)

    await log_event(db, "GITHUB_LOGIN", request, user_id=user.id, details={"email": gh_email})

    if user.mfa_enabled:
        mfa_token = create_mfa_pending_token({"sub": str(user.id)})
        return {"mfa_required": True, "mfa_token": mfa_token, "token_type": "bearer"}

    access_token = create_access_token({"sub": str(user.id)})
    refresh_token = create_refresh_token({"sub": str(user.id)})
    return {"access_token": access_token, "refresh_token": refresh_token, "token_type": "bearer", "mfa_required": False}
