from fastapi import APIRouter, Depends, Header, HTTPException, status
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.database import get_db
from app.models.notification_preference import NotificationPreference
from app.models.user import User
from app.routers.auth import get_current_user
from app.services.email_service import EmailService

router = APIRouter()


# ── Schemas ──────────────────────────────────────────────────────

class PreferencesResponse(BaseModel):
    digest_enabled: bool
    digest_day: str
    alert_budget_exceeded: bool
    alert_large_transaction: bool
    alert_large_transaction_threshold: float
    alert_anomaly: bool

    model_config = {"from_attributes": True}


class PreferencesUpdate(BaseModel):
    digest_enabled: bool | None = None
    digest_day: str | None = None
    alert_budget_exceeded: bool | None = None
    alert_large_transaction: bool | None = None
    alert_large_transaction_threshold: float | None = None
    alert_anomaly: bool | None = None


# ── Helpers ──────────────────────────────────────────────────────

async def _get_or_create_prefs(user_id, db: AsyncSession) -> NotificationPreference:
    result = await db.execute(
        select(NotificationPreference).where(NotificationPreference.user_id == user_id)
    )
    prefs = result.scalar_one_or_none()
    if not prefs:
        prefs = NotificationPreference(user_id=user_id)
        db.add(prefs)
        await db.commit()
        await db.refresh(prefs)
    return prefs


# ── Endpoints ────────────────────────────────────────────────────

@router.get("/preferences", response_model=PreferencesResponse)
async def get_preferences(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    prefs = await _get_or_create_prefs(current_user.id, db)
    return PreferencesResponse.model_validate(prefs)


@router.put("/preferences", response_model=PreferencesResponse)
async def update_preferences(
    body: PreferencesUpdate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    prefs = await _get_or_create_prefs(current_user.id, db)

    for field, value in body.model_dump(exclude_unset=True).items():
        setattr(prefs, field, value)

    await db.commit()
    await db.refresh(prefs)
    return PreferencesResponse.model_validate(prefs)


@router.post("/test-digest")
async def test_digest(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    email_service = EmailService()
    sent = await email_service.send_digest(current_user, db)
    if not sent:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to send digest email. Check that RESEND_API_KEY is configured.",
        )
    return {"message": "Digest email sent", "to": current_user.email}


@router.post("/digest")
async def trigger_digest(
    x_scheduler_secret: str = Header(...),
    db: AsyncSession = Depends(get_db),
):
    if x_scheduler_secret != settings.scheduler_secret:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Invalid scheduler secret")

    # Find all users with digest enabled
    result = await db.execute(
        select(User)
        .join(NotificationPreference, NotificationPreference.user_id == User.id)
        .where(NotificationPreference.digest_enabled.is_(True))
    )
    users = result.scalars().all()

    email_service = EmailService()
    sent_count = 0
    for user in users:
        success = await email_service.send_digest(user, db)
        if success:
            sent_count += 1

    return {"sent": sent_count, "total_eligible": len(users)}
