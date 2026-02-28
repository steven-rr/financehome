import uuid
from datetime import date

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.models.insight import InsightCache
from app.models.user import User
from app.routers.auth import get_current_user
from app.services.claude_service import InsightsService

router = APIRouter()


class GenerateInsightRequest(BaseModel):
    insight_type: str  # spending_summary | anomalies | forecast | category_analysis | recommendations
    start_date: date
    end_date: date
    provider: str = "gemini"  # "gemini" | "anthropic"


class InsightResponse(BaseModel):
    id: uuid.UUID
    insight_type: str
    period_start: date
    period_end: date
    content: dict
    generated_at: str

    model_config = {"from_attributes": True}


class AskRequest(BaseModel):
    question: str
    start_date: date | None = None
    end_date: date | None = None
    provider: str = "gemini"  # "gemini" | "anthropic"


class AskResponse(BaseModel):
    answer: str


@router.post("/generate", response_model=InsightResponse)
async def generate_insight(
    request: GenerateInsightRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    service = InsightsService()
    insight = await service.generate_insight(
        user_id=current_user.id,
        insight_type=request.insight_type,
        start_date=request.start_date,
        end_date=request.end_date,
        db=db,
        provider=request.provider,
    )
    return InsightResponse(
        id=insight.id,
        insight_type=insight.insight_type,
        period_start=insight.period_start,
        period_end=insight.period_end,
        content=insight.content,
        generated_at=insight.generated_at.isoformat(),
    )


@router.get("", response_model=list[InsightResponse])
async def list_insights(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    insight_type: str | None = Query(None),
):
    query = select(InsightCache).where(InsightCache.user_id == current_user.id)
    if insight_type:
        query = query.where(InsightCache.insight_type == insight_type)
    query = query.order_by(InsightCache.generated_at.desc()).limit(20)

    result = await db.execute(query)
    insights = result.scalars().all()
    return [
        InsightResponse(
            id=i.id,
            insight_type=i.insight_type,
            period_start=i.period_start,
            period_end=i.period_end,
            content=i.content,
            generated_at=i.generated_at.isoformat(),
        )
        for i in insights
    ]


@router.post("/ask", response_model=AskResponse)
async def ask_question(
    request: AskRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    service = InsightsService()
    answer = await service.ask_about_finances(
        user_id=current_user.id,
        question=request.question,
        start_date=request.start_date,
        end_date=request.end_date,
        db=db,
        provider=request.provider,
    )
    return AskResponse(answer=answer)
