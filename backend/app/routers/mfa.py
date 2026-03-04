import base64
import hashlib
import io
import json
import secrets
import uuid
from datetime import datetime, timezone

import pyotp
import qrcode
from fastapi import APIRouter, Depends, HTTPException, Request, status
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.models.user import User
from app.rate_limit import limiter
from app.routers.auth import get_current_user
from app.utils.encryption import decrypt_token, encrypt_token
from app.utils.security import (
    create_access_token,
    create_mfa_pending_token,
    create_refresh_token,
    decode_token,
)

router = APIRouter()

RECOVERY_CODE_COUNT = 8


# ── Schemas ──────────────────────────────────────────────────────


class MFAStatusResponse(BaseModel):
    mfa_enabled: bool
    mfa_enabled_at: str | None = None


class MFASetupResponse(BaseModel):
    secret: str
    qr_code_data_uri: str


class MFAConfirmRequest(BaseModel):
    code: str


class MFAConfirmResponse(BaseModel):
    recovery_codes: list[str]


class MFAVerifyRequest(BaseModel):
    mfa_token: str
    code: str


class MFADisableRequest(BaseModel):
    code: str


class MFARegenerateRequest(BaseModel):
    code: str


# ── Helpers ──────────────────────────────────────────────────────


def _generate_recovery_codes() -> list[str]:
    """Generate 8 recovery codes in xxxx-xxxx format."""
    codes = []
    for _ in range(RECOVERY_CODE_COUNT):
        raw = secrets.token_hex(4)  # 8 hex chars
        codes.append(f"{raw[:4]}-{raw[4:]}")
    return codes


def _hash_code(code: str) -> str:
    return hashlib.sha256(code.encode()).hexdigest()


def _store_recovery_codes(user: User, plaintext_codes: list[str]) -> None:
    """Hash codes and store encrypted JSON array."""
    hashed = [_hash_code(c) for c in plaintext_codes]
    user.mfa_recovery_codes_encrypted = encrypt_token(json.dumps(hashed))


def _consume_recovery_code(user: User, code: str) -> bool:
    """Check if code matches a stored recovery code. If so, consume it."""
    if not user.mfa_recovery_codes_encrypted:
        return False
    hashed_codes: list[str] = json.loads(decrypt_token(user.mfa_recovery_codes_encrypted))
    code_hash = _hash_code(code.strip().lower())
    if code_hash in hashed_codes:
        hashed_codes.remove(code_hash)
        user.mfa_recovery_codes_encrypted = encrypt_token(json.dumps(hashed_codes))
        return True
    return False


def _generate_qr_data_uri(provisioning_uri: str) -> str:
    """Generate a QR code as a base64 data URI."""
    img = qrcode.make(provisioning_uri)
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    b64 = base64.b64encode(buf.getvalue()).decode()
    return f"data:image/png;base64,{b64}"


# ── Endpoints ────────────────────────────────────────────────────


@router.get("/status", response_model=MFAStatusResponse)
@limiter.limit("30/minute")
async def mfa_status(request: Request, current_user: User = Depends(get_current_user)):
    return MFAStatusResponse(
        mfa_enabled=bool(current_user.mfa_enabled),
        mfa_enabled_at=current_user.mfa_enabled_at.isoformat() if current_user.mfa_enabled_at else None,
    )


@router.post("/setup", response_model=MFASetupResponse)
@limiter.limit("5/minute")
async def mfa_setup(
    request: Request,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    if current_user.mfa_enabled:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="MFA is already enabled")

    secret = pyotp.random_base32()
    totp = pyotp.TOTP(secret)
    provisioning_uri = totp.provisioning_uri(name=current_user.email, issuer_name="FinanceHome")

    # Store encrypted secret (not yet enabled)
    current_user.mfa_secret_encrypted = encrypt_token(secret)
    await db.commit()

    qr_data_uri = _generate_qr_data_uri(provisioning_uri)

    return MFASetupResponse(secret=secret, qr_code_data_uri=qr_data_uri)


@router.post("/confirm", response_model=MFAConfirmResponse)
@limiter.limit("10/minute")
async def mfa_confirm(
    request: Request,
    body: MFAConfirmRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    if current_user.mfa_enabled:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="MFA is already enabled")
    if not current_user.mfa_secret_encrypted:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Call /setup first")

    secret = decrypt_token(current_user.mfa_secret_encrypted)
    totp = pyotp.TOTP(secret)

    if not totp.verify(body.code, valid_window=1):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid code")

    # Enable MFA
    current_user.mfa_enabled = True
    current_user.mfa_enabled_at = datetime.now(timezone.utc)

    # Generate and store recovery codes
    recovery_codes = _generate_recovery_codes()
    _store_recovery_codes(current_user, recovery_codes)
    await db.commit()

    return MFAConfirmResponse(recovery_codes=recovery_codes)


@router.post("/verify")
@limiter.limit("5/minute")
async def mfa_verify(
    request: Request,
    body: MFAVerifyRequest,
    db: AsyncSession = Depends(get_db),
):
    # Decode the MFA pending token
    payload = decode_token(body.mfa_token)
    if not payload or payload.get("type") != "mfa_pending":
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid or expired MFA token")

    user_id = payload.get("sub")
    result = await db.execute(select(User).where(User.id == uuid.UUID(user_id)))
    user = result.scalar_one_or_none()
    if not user or not user.mfa_enabled or not user.mfa_secret_encrypted:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid MFA state")

    # Try TOTP code first
    secret = decrypt_token(user.mfa_secret_encrypted)
    totp = pyotp.TOTP(secret)

    if totp.verify(body.code, valid_window=1):
        access_token = create_access_token({"sub": str(user.id)})
        refresh_token = create_refresh_token({"sub": str(user.id)})
        return {"access_token": access_token, "refresh_token": refresh_token, "token_type": "bearer", "mfa_required": False}

    # Try recovery code (they contain a dash, TOTP codes don't)
    if "-" in body.code:
        if _consume_recovery_code(user, body.code):
            await db.commit()
            access_token = create_access_token({"sub": str(user.id)})
            refresh_token = create_refresh_token({"sub": str(user.id)})
            return {"access_token": access_token, "refresh_token": refresh_token, "token_type": "bearer", "mfa_required": False}

    raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid code")


@router.post("/disable")
@limiter.limit("5/minute")
async def mfa_disable(
    request: Request,
    body: MFADisableRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    if not current_user.mfa_enabled or not current_user.mfa_secret_encrypted:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="MFA is not enabled")

    secret = decrypt_token(current_user.mfa_secret_encrypted)
    totp = pyotp.TOTP(secret)

    if not totp.verify(body.code, valid_window=1):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid code")

    current_user.mfa_enabled = False
    current_user.mfa_secret_encrypted = None
    current_user.mfa_recovery_codes_encrypted = None
    current_user.mfa_enabled_at = None
    await db.commit()

    return {"message": "MFA disabled"}


@router.post("/recovery-codes/regenerate", response_model=MFAConfirmResponse)
@limiter.limit("3/minute")
async def regenerate_recovery_codes(
    request: Request,
    body: MFARegenerateRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    if not current_user.mfa_enabled or not current_user.mfa_secret_encrypted:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="MFA is not enabled")

    secret = decrypt_token(current_user.mfa_secret_encrypted)
    totp = pyotp.TOTP(secret)

    if not totp.verify(body.code, valid_window=1):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid code")

    recovery_codes = _generate_recovery_codes()
    _store_recovery_codes(current_user, recovery_codes)
    await db.commit()

    return MFAConfirmResponse(recovery_codes=recovery_codes)
