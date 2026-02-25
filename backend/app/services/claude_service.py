import json
import uuid
from datetime import date

import anthropic
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.models.insight import InsightCache
from app.services.analytics_service import AnalyticsService


class ClaudeService:
    def __init__(self):
        self.client = anthropic.Anthropic(api_key=settings.anthropic_api_key)
        self.analytics = AnalyticsService()
        self.model = "claude-sonnet-4-6-20250514"

    async def generate_insight(
        self,
        user_id: uuid.UUID,
        insight_type: str,
        start_date: date,
        end_date: date,
        db: AsyncSession,
    ) -> InsightCache:
        transactions = await self.analytics.get_transactions_for_period(user_id, start_date, end_date, db)
        spending = await self.analytics.get_spending_by_category(user_id, start_date, end_date, db)
        income_expenses = await self.analytics.get_income_vs_expenses(user_id, start_date, end_date, db)

        context = {
            "period": f"{start_date} to {end_date}",
            "transaction_count": len(transactions),
            "spending_by_category": spending,
            "income_vs_expenses": income_expenses,
            "recent_transactions": transactions[:100],
        }

        prompt = self._build_prompt(insight_type, context)
        response = self.client.messages.create(
            model=self.model,
            max_tokens=2000,
            messages=[{"role": "user", "content": prompt}],
        )

        content_text = response.content[0].text
        try:
            parsed_content = json.loads(content_text)
        except json.JSONDecodeError:
            parsed_content = {"raw_response": content_text}

        insight = InsightCache(
            user_id=user_id,
            insight_type=insight_type,
            period_start=start_date,
            period_end=end_date,
            content=parsed_content,
        )
        db.add(insight)
        await db.commit()
        await db.refresh(insight)

        return insight

    async def ask_about_finances(
        self,
        user_id: uuid.UUID,
        question: str,
        start_date: date | None,
        end_date: date | None,
        db: AsyncSession,
    ) -> str:
        if not start_date:
            start_date = date.today().replace(day=1)
        if not end_date:
            end_date = date.today()

        transactions = await self.analytics.get_transactions_for_period(user_id, start_date, end_date, db)
        spending = await self.analytics.get_spending_by_category(user_id, start_date, end_date, db)
        income_expenses = await self.analytics.get_income_vs_expenses(user_id, start_date, end_date, db)
        net_worth = await self.analytics.get_net_worth(user_id, db)

        prompt = f"""You are a personal finance assistant for FinanceHome. Answer the user's question based on their financial data.

Financial Data ({start_date} to {end_date}):
- Income: ${income_expenses['income']:,.2f}
- Expenses: ${income_expenses['expenses']:,.2f}
- Net: ${income_expenses['net']:,.2f}
- Net Worth: ${net_worth['net_worth']:,.2f} (Assets: ${net_worth['assets']:,.2f}, Liabilities: ${net_worth['liabilities']:,.2f})

Spending by Category:
{json.dumps(spending, indent=2)}

Recent Transactions (last 50):
{json.dumps(transactions[:50], indent=2)}

User's Question: {question}

Provide a clear, helpful answer. Use specific numbers from the data. Be concise."""

        response = self.client.messages.create(
            model=self.model,
            max_tokens=1500,
            messages=[{"role": "user", "content": prompt}],
        )

        return response.content[0].text

    def _build_prompt(self, insight_type: str, context: dict) -> str:
        base_context = f"""Analyze the following financial data for the period {context['period']}.

Transaction count: {context['transaction_count']}
Income: ${context['income_vs_expenses']['income']:,.2f}
Expenses: ${context['income_vs_expenses']['expenses']:,.2f}
Net: ${context['income_vs_expenses']['net']:,.2f}

Spending by Category:
{json.dumps(context['spending_by_category'], indent=2)}

Recent Transactions:
{json.dumps(context['recent_transactions'][:50], indent=2)}
"""

        prompts = {
            "spending_summary": f"""{base_context}

Provide a spending summary. Return valid JSON with this structure:
{{"summary": "2-3 sentence overview", "highlights": ["highlight 1", "highlight 2", "highlight 3"], "top_categories": [{{"name": "category", "amount": 123.45, "percentage": 25.5}}], "comparison_note": "comparison to typical spending"}}""",
            "anomalies": f"""{base_context}

Identify unusual or anomalous transactions. Return valid JSON with this structure:
{{"anomalies": [{{"description": "what is unusual", "merchant": "merchant name", "amount": 123.45, "date": "2024-01-01", "severity": "low|medium|high", "reason": "why this is unusual"}}], "summary": "brief overview of findings"}}""",
            "forecast": f"""{base_context}

Based on spending patterns, forecast the next 30 days. Return valid JSON with this structure:
{{"projected_expenses": 1234.56, "projected_income": 2345.67, "projected_net": 1111.11, "recurring_expenses": [{{"description": "expense", "amount": 123.45, "frequency": "monthly"}}], "advice": "brief financial advice"}}""",
            "category_analysis": f"""{base_context}

Provide a deep analysis of spending categories. Return valid JSON with this structure:
{{"categories": [{{"name": "category", "total": 123.45, "percentage": 25.5, "trend": "increasing|stable|decreasing", "insight": "brief insight"}}], "summary": "overall analysis"}}""",
            "recommendations": f"""{base_context}

Provide actionable financial recommendations. Return valid JSON with this structure:
{{"recommendations": [{{"title": "recommendation title", "description": "detailed description", "potential_savings": 123.45, "priority": "high|medium|low"}}], "summary": "overall financial health assessment"}}""",
        }

        return prompts.get(insight_type, prompts["spending_summary"])
