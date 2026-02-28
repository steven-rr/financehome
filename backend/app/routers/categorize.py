from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.models.user import User
from app.routers.auth import get_current_user
from app.services.gemini_categorizer import GeminiCategorizer

router = APIRouter()


@router.post("/run")
async def run_categorization(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    categorizer = GeminiCategorizer()
    result = await categorizer.categorize_uncategorized(current_user.id, db)
    return result
