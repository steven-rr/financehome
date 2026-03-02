import json
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


class SubscriptionInsightsResponse(BaseModel):
    insights: list[str]
    generated_at: str


@router.get("/insights", response_model=SubscriptionInsightsResponse)
async def get_subscription_insights(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    refresh: bool = Query(False),
):
    # Check cache (generated today) unless refresh requested
    if not refresh:
        cached = await db.execute(
            select(InsightCache)
            .where(
                InsightCache.user_id == current_user.id,
                InsightCache.insight_type == "subscription_insights",
                InsightCache.generated_at >= date.today(),
            )
            .order_by(InsightCache.generated_at.desc())
            .limit(1)
        )
        existing = cached.scalar_one_or_none()
        if existing:
            return SubscriptionInsightsResponse(
                insights=existing.content.get("insights", []),
                generated_at=existing.generated_at.isoformat(),
            )

    # Get recurring data
    recurring_service = RecurringService()
    recurring = await recurring_service.detect_recurring(user_id=current_user.id, db=db)

    if not recurring["items"]:
        return SubscriptionInsightsResponse(
            insights=["Not enough transaction history to analyze subscriptions yet."],
            generated_at=date.today().isoformat(),
        )

    # Build category summary, separating fixed bills from discretionary subscriptions
    FIXED_BILL_CATEGORIES = {"Rent", "Mortgage", "Utilities", "Phone & Internet", "Insurance"}
    multipliers = {"weekly": 4.33, "bi-weekly": 2.17, "monthly": 1.0, "quarterly": 0.33, "annual": 0.083}

    subscriptions = []
    fixed_bills = []
    cat_totals: dict[str, float] = {}
    for item in recurring["items"]:
        cat = item["category"]
        monthly = item["amount"] * multipliers.get(item["frequency"], 1.0)
        cat_totals[cat] = cat_totals.get(cat, 0.0) + monthly
        if cat in FIXED_BILL_CATEGORIES:
            fixed_bills.append(item)
        else:
            subscriptions.append(item)

    sub_monthly = sum(
        i["amount"] * multipliers.get(i["frequency"], 1.0) for i in subscriptions
    )
    fixed_monthly = sum(
        i["amount"] * multipliers.get(i["frequency"], 1.0) for i in fixed_bills
    )
    cat_totals_sorted = {k: round(v, 2) for k, v in sorted(cat_totals.items(), key=lambda x: -x[1])}

    prompt = f"""You are a personal finance advisor. Analyze this person's recurring charges.

IMPORTANT: Separate fixed bills (rent, utilities, insurance, phone) from discretionary subscriptions (streaming, software, gym, memberships) in your analysis. The US benchmark of $273/month only covers discretionary subscriptions — do NOT compare rent/mortgage against that number.

Discretionary Subscriptions ({len(subscriptions)} items, ${sub_monthly:.2f}/month):
{json.dumps(subscriptions, indent=2, default=str)}

Fixed Bills ({len(fixed_bills)} items, ${fixed_monthly:.2f}/month):
{json.dumps(fixed_bills, indent=2, default=str)}

Total recurring: ${recurring['total_monthly_cost']:.2f}/month (${recurring['total_monthly_cost'] * 12:.2f}/year)

Monthly cost by category:
{json.dumps(cat_totals_sorted, indent=2)}

US Household Benchmarks (subscriptions only, excludes rent/utilities):
- Average US household spends ~$273/month on subscriptions (2024)
- Streaming: avg $61/month across 4 services
- Software/cloud: avg $30/month
- Gym/fitness: avg $50/month
- News/media: avg $15/month

Generate 8-10 concise, actionable insights as a JSON array of strings. Include a mix:
1. How their total compares to US averages (above/below, by how much)
2. Per-category comparisons where they're spending notably more or less than typical
3. Potential savings opportunities (overlapping services, cheaper alternatives)
4. Positive observations about categories where they're doing well
5. Negative observations — categories where they're overspending or could do better, with specific dollar amounts
6. Any subscription that seems unusually expensive for its category
7. Redundant or overlapping services they could consolidate
8. Price trends — any subscriptions that may have increased recently
9. A concrete savings target if applicable

Use specific dollar amounts. Keep each insight to 1-2 sentences. Be direct and helpful, not generic.
Example: ["Your streaming costs ($45/mo) are below the US average of $61/mo — good job keeping those in check.", "Software & Apps at $45/mo is $15 above the typical $30/mo — review if all three services are essential."]"""

    ai_service = InsightsService()
    try:
        response_text = await ai_service._call_gemini(prompt, temperature=0.3, json_mode=True)
        insights = json.loads(response_text)
        if not isinstance(insights, list):
            insights = insights.get("insights", []) if isinstance(insights, dict) else []
    except Exception:
        insights = ["Unable to generate subscription insights at this time."]

    # Cache
    cache_entry = InsightCache(
        user_id=current_user.id,
        insight_type="subscription_insights",
        period_start=date.today(),
        period_end=date.today(),
        content={"insights": insights},
    )
    db.add(cache_entry)
    await db.commit()
    await db.refresh(cache_entry)

    return SubscriptionInsightsResponse(
        insights=insights,
        generated_at=cache_entry.generated_at.isoformat(),
    )
