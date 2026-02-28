import uuid

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.models.budget import Budget
from app.models.user import User
from app.routers.auth import get_current_user

router = APIRouter()


class BudgetRequest(BaseModel):
    category: str
    monthly_limit: float


class BudgetResponse(BaseModel):
    id: uuid.UUID
    category: str
    monthly_limit: float

    model_config = {"from_attributes": True}


@router.get("", response_model=list[BudgetResponse])
async def list_budgets(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(Budget)
        .where(Budget.user_id == current_user.id)
        .order_by(Budget.category)
    )
    return [BudgetResponse.model_validate(b) for b in result.scalars().all()]


@router.put("", response_model=BudgetResponse)
async def upsert_budget(
    request: BudgetRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    if request.monthly_limit <= 0:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="monthly_limit must be positive",
        )

    result = await db.execute(
        select(Budget).where(
            Budget.user_id == current_user.id,
            Budget.category == request.category,
        )
    )
    budget = result.scalar_one_or_none()

    if budget:
        budget.monthly_limit = request.monthly_limit
    else:
        budget = Budget(
            user_id=current_user.id,
            category=request.category,
            monthly_limit=request.monthly_limit,
        )
        db.add(budget)

    await db.commit()
    await db.refresh(budget)
    return BudgetResponse.model_validate(budget)


@router.delete("/{category}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_budget(
    category: str,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(Budget).where(
            Budget.user_id == current_user.id,
            Budget.category == category,
        )
    )
    budget = result.scalar_one_or_none()
    if not budget:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Budget not found",
        )
    await db.delete(budget)
    await db.commit()
