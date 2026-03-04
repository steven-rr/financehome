from fastapi import APIRouter, Body, Depends, HTTPException, Request
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.database import get_db
from app.models.user import User
from app.rate_limit import limiter
from app.routers.auth import get_current_user
from app.services.gemini_categorizer import TransactionCategorizer

router = APIRouter()


@router.post("/run")
@limiter.limit("5/minute")
async def run_categorization(
    request: Request,
    provider: str = Body("gemini", embed=True),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    if provider == "anthropic" and current_user.email.lower() not in settings.admin_emails_set:
        provider = "gemini"
    categorizer = TransactionCategorizer()
    result = await categorizer.categorize_uncategorized(current_user.id, db, provider=provider)
    return result


@router.post("/recategorize-all")
@limiter.limit("2/minute")
async def recategorize_all(
    request: Request,
    provider: str = Body("gemini", embed=True),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Admin-only: re-evaluate ALL transactions (except user_category overrides)."""
    if current_user.email.lower() not in settings.admin_emails_set:
        raise HTTPException(status_code=403, detail="Admin only")
    if provider == "anthropic" and current_user.email.lower() not in settings.admin_emails_set:
        provider = "gemini"
    categorizer = TransactionCategorizer()
    result = await categorizer.recategorize_all(current_user.id, db, provider=provider)
    return result
