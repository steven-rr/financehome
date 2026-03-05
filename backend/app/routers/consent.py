import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Request, status
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.models.consent_record import ConsentRecord
from app.rate_limit import limiter
from app.routers.auth import get_current_user
from app.models.user import User
from app.services.audit import log_event

router = APIRouter()


class GrantConsentRequest(BaseModel):
    consent_type: str
    consent_version: str


class ConsentRecordResponse(BaseModel):
    id: uuid.UUID
    consent_type: str
    consent_version: str
    granted_at: datetime
    revoked_at: datetime | None

    model_config = {"from_attributes": True}


class ConsentStatusResponse(BaseModel):
    has_consent: bool
    consent: ConsentRecordResponse | None = None


class RevokeConsentRequest(BaseModel):
    consent_id: uuid.UUID


@router.post("/grant", response_model=ConsentRecordResponse, status_code=status.HTTP_201_CREATED)
@limiter.limit("10/minute")
async def grant_consent(
    request: Request,
    body: GrantConsentRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    record = ConsentRecord(
        user_id=current_user.id,
        consent_type=body.consent_type,
        consent_version=body.consent_version,
        ip_address=request.client.host if request.client else None,
        user_agent=(request.headers.get("user-agent", "") or "")[:512] or None,
    )
    db.add(record)
    await db.commit()
    await db.refresh(record)

    await log_event(
        db, "CONSENT_GRANTED", request,
        user_id=current_user.id,
        details={"consent_type": body.consent_type, "consent_version": body.consent_version},
    )

    return record


@router.post("/revoke")
@limiter.limit("10/minute")
async def revoke_consent(
    request: Request,
    body: RevokeConsentRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(ConsentRecord).where(
            ConsentRecord.id == body.consent_id,
            ConsentRecord.user_id == current_user.id,
        )
    )
    record = result.scalar_one_or_none()
    if not record:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Consent record not found")

    if record.revoked_at:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Consent already revoked")

    record.revoked_at = datetime.now(timezone.utc)
    await db.commit()

    await log_event(
        db, "CONSENT_REVOKED", request,
        user_id=current_user.id,
        details={"consent_type": record.consent_type, "consent_id": str(record.id)},
    )

    return {"message": "Consent revoked"}


@router.get("/status", response_model=ConsentStatusResponse)
@limiter.limit("30/minute")
async def consent_status(
    request: Request,
    consent_type: str,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(ConsentRecord)
        .where(
            ConsentRecord.user_id == current_user.id,
            ConsentRecord.consent_type == consent_type,
            ConsentRecord.revoked_at.is_(None),
        )
        .order_by(ConsentRecord.granted_at.desc())
        .limit(1)
    )
    record = result.scalar_one_or_none()

    if record:
        return ConsentStatusResponse(has_consent=True, consent=ConsentRecordResponse.model_validate(record))
    return ConsentStatusResponse(has_consent=False)


@router.get("/history", response_model=list[ConsentRecordResponse])
@limiter.limit("30/minute")
async def consent_history(
    request: Request,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(ConsentRecord)
        .where(ConsentRecord.user_id == current_user.id)
        .order_by(ConsentRecord.granted_at.desc())
    )
    return result.scalars().all()
