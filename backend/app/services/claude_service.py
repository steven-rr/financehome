import asyncio
import json
import uuid
from datetime import date

import anthropic
from google import genai
from google.genai import types
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.models.insight import InsightCache
from app.services.analytics_service import AnalyticsService


class InsightsService:
    """Financial insights service supporting Gemini (free) and Claude (paid)."""

    def __init__(self):
        self.gemini_client = genai.Client(api_key=settings.gemini_api_key)
        self.analytics = AnalyticsService()

        self.anthropic_client = None
        if settings.anthropic_api_key:
            self.anthropic_client = anthropic.AsyncAnthropic(api_key=settings.anthropic_api_key)

    async def _call_gemini(self, prompt: str, temperature: float = 0.3, json_mode: bool = False) -> str:
        config = types.GenerateContentConfig(temperature=temperature)
        if json_mode:
            config.response_mime_type = "application/json"
        response = await asyncio.to_thread(
            self.gemini_client.models.generate_content,
            model="gemini-2.5-flash",
            contents=prompt,
            config=config,
        )
        return response.text

    async def _call_anthropic(self, prompt: str, temperature: float = 0.3, json_mode: bool = False) -> str:
        system_msg = "You are a personal finance analyst for FinanceHome."
        if json_mode:
            system_msg += " You MUST respond with ONLY valid JSON. No markdown fencing, no explanation, just the JSON object."
        response = await self.anthropic_client.messages.create(
            model="claude-sonnet-4-5-20250514",
            max_tokens=4096,
            temperature=temperature,
            system=system_msg,
            messages=[{"role": "user", "content": prompt}],
        )
        text = response.content[0].text.strip()
        # Strip markdown fences if present
        if json_mode and text.startswith("```"):
            text = text.split("\n", 1)[1] if "\n" in text else text[3:]
            if text.endswith("```"):
                text = text[:-3].strip()
        return text

    async def generate_insight(
        self,
        user_id: uuid.UUID,
        insight_type: str,
        start_date: date,
        end_date: date,
        db: AsyncSession,
        provider: str = "gemini",
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

        if provider == "anthropic" and self.anthropic_client:
            content_text = await self._call_anthropic(prompt, temperature=0.3, json_mode=True)
        else:
            content_text = await self._call_gemini(prompt, temperature=0.3, json_mode=True)

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
        provider: str = "gemini",
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

        if provider == "anthropic" and self.anthropic_client:
            return await self._call_anthropic(prompt, temperature=0.3)
        else:
            return await self._call_gemini(prompt, temperature=0.3)

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


# Backward compatibility alias
ClaudeService = InsightsService
