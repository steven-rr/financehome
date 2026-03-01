from fastapi import APIRouter, Body, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.database import get_db
from app.models.user import User
from app.routers.auth import get_current_user
from app.services.gemini_categorizer import TransactionCategorizer

router = APIRouter()


@router.post("/run")
async def run_categorization(
    provider: str = Body("gemini", embed=True),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    if provider == "anthropic" and current_user.email.lower() not in settings.admin_emails_set:
        provider = "gemini"
    categorizer = TransactionCategorizer()
    result = await categorizer.categorize_uncategorized(current_user.id, db, provider=provider)
    return result
