from datetime import date

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.models.user import User
from app.routers.auth import get_current_user
from app.services.recurring_service import RecurringService

router = APIRouter()


class RecurringItemResponse(BaseModel):
    merchant: str
    amount: float
    frequency: str
    category: str
    confidence: float
    last_date: date
    occurrence_count: int


class RecurringResponse(BaseModel):
    total_monthly_cost: float
    items: list[RecurringItemResponse]


@router.get("", response_model=RecurringResponse)
async def get_recurring_transactions(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    service = RecurringService()
    return await service.detect_recurring(user_id=current_user.id, db=db)
