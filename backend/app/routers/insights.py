import json
import uuid
from datetime import date, timedelta

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.models.insight import InsightCache
from app.models.user import User
from app.routers.auth import get_current_user
from app.services.analytics_service import AnalyticsService
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


class SpendingInsightsResponse(BaseModel):
    insights: list[str]
    generated_at: str


@router.get("/spending-insights", response_model=SpendingInsightsResponse)
async def get_spending_insights(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    today = date.today()

    # Check for cached insights generated today
    cached = await db.execute(
        select(InsightCache)
        .where(
            InsightCache.user_id == current_user.id,
            InsightCache.insight_type == "spending_insights",
            InsightCache.generated_at >= today,
        )
        .order_by(InsightCache.generated_at.desc())
        .limit(1)
    )
    existing = cached.scalar_one_or_none()
    if existing:
        return SpendingInsightsResponse(
            insights=existing.content.get("insights", []),
            generated_at=existing.generated_at.isoformat(),
        )

    # Compute current month vs previous month data
    current_month_start = today.replace(day=1)
    prev_month_end = current_month_start - timedelta(days=1)
    prev_month_start = prev_month_end.replace(day=1)

    analytics = AnalyticsService()
    current_spending = await analytics.get_spending_by_category(current_user.id, current_month_start, today, db)
    prev_spending = await analytics.get_spending_by_category(current_user.id, prev_month_start, prev_month_end, db)
    current_income = await analytics.get_income_vs_expenses(current_user.id, current_month_start, today, db)
    prev_income = await analytics.get_income_vs_expenses(current_user.id, prev_month_start, prev_month_end, db)

    prompt = f"""You are a personal finance analyst. Compare this month's spending to last month's and generate observations.

This Month ({current_month_start.strftime('%B %Y')}, {today.day} days in):
- Income: ${current_income['income']:,.2f}, Expenses: ${current_income['expenses']:,.2f}, Net: ${current_income['net']:,.2f}
- Spending by category: {json.dumps(current_spending)}

Last Month ({prev_month_start.strftime('%B %Y')}, full month):
- Income: ${prev_income['income']:,.2f}, Expenses: ${prev_income['expenses']:,.2f}, Net: ${prev_income['net']:,.2f}
- Spending by category: {json.dumps(prev_spending)}

Generate 4-5 concise, specific observations as a JSON array of strings.
Focus on: notable month-over-month changes, trends, largest spending categories, areas of concern or improvement.
Use specific dollar amounts and percentages. Keep each observation to 1 sentence.
Account for the fact that the current month may not be complete yet when comparing totals.
Example format: ["Restaurants spending is up 35% ($420 vs $310 last month).", "Grocery spending dropped by $85 compared to last month."]"""

    service = InsightsService()
    try:
        response_text = await service._call_gemini(prompt, temperature=0.3, json_mode=True)
        insights = json.loads(response_text)
        if not isinstance(insights, list):
            insights = insights.get("insights", []) if isinstance(insights, dict) else []
    except Exception:
        insights = ["Unable to generate insights at this time. Try again later."]

    # Cache the result
    cache_entry = InsightCache(
        user_id=current_user.id,
        insight_type="spending_insights",
        period_start=prev_month_start,
        period_end=today,
        content={"insights": insights},
    )
    db.add(cache_entry)
    await db.commit()
    await db.refresh(cache_entry)

    return SpendingInsightsResponse(
        insights=insights,
        generated_at=cache_entry.generated_at.isoformat(),
    )
