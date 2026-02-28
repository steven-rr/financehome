import asyncio
import json
import logging
import uuid

import anthropic
from google import genai
from google.genai import types
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.models.account import Account
from app.models.transaction import Transaction
from app.services.analytics_service import CREDIT_CARD_PAYMENT_PATTERNS

logger = logging.getLogger(__name__)


def _is_cc_payment_desc(description: str) -> bool:
    """Check if a transaction description matches a known CC payment pattern."""
    desc_upper = description.upper()
    return any(p.upper() in desc_upper for p in CREDIT_CARD_PAYMENT_PATTERNS)

VALID_CATEGORIES = [
    "Groceries",
    "Restaurants",
    "Coffee & Drinks",
    "Entertainment",
    "Shopping",
    "Transportation",
    "Gas & Fuel",
    "Utilities",
    "Rent & Mortgage",
    "Insurance",
    "Healthcare",
    "Personal Care",
    "Education",
    "Subscriptions",
    "Travel",
    "Gifts & Donations",
    "Fees & Charges",
    "Other",
]

BATCH_SIZE = 50


def _build_categorize_prompt(txn_list: list[dict]) -> str:
    return f"""Categorize each transaction into exactly one of these categories:
{json.dumps(VALID_CATEGORIES)}

Transactions:
{json.dumps(txn_list)}

Respond with ONLY a JSON array of objects, one per transaction, in the same order.
Each object must have "id" (the index) and "category" (one of the valid categories above).
Example: [{{"id": 0, "category": "Groceries"}}, {{"id": 1, "category": "Restaurants"}}]"""


def _build_txn_list(transactions: list[Transaction]) -> list[dict]:
    return [
        {
            "id": idx,
            "description": txn.description,
            "merchant": txn.merchant_name or "",
            "amount": float(txn.amount),
        }
        for idx, txn in enumerate(transactions)
    ]


class TransactionCategorizer:
    def __init__(self):
        self.gemini_client = genai.Client(api_key=settings.gemini_api_key)

        self.anthropic_client = None
        if settings.anthropic_api_key:
            self.anthropic_client = anthropic.AsyncAnthropic(api_key=settings.anthropic_api_key)

    async def categorize_uncategorized(
        self,
        user_id: uuid.UUID,
        db: AsyncSession,
        provider: str = "gemini",
        model: str | None = None,
    ) -> dict:
        """Find all transactions with no category and no ai_category, then batch-categorize."""
        result = await db.execute(
            select(Transaction)
            .join(Account, Transaction.account_id == Account.id)
            .where(
                Account.user_id == user_id,
                Transaction.category.is_(None),
                Transaction.ai_category.is_(None),
            )
        )
        transactions = result.scalars().all()

        if not transactions:
            return {"categorized": 0, "total_uncategorized": 0}

        # Pre-tag CC payments so they don't get sent to AI as "Other"
        need_ai = []
        for txn in transactions:
            if _is_cc_payment_desc(txn.description):
                txn.ai_category = "Payment"
            else:
                need_ai.append(txn)

        cc_tagged = len(transactions) - len(need_ai)
        categorized_count = cc_tagged
        total = len(transactions)

        use_anthropic = provider == "anthropic" and self.anthropic_client

        for i in range(0, len(need_ai), BATCH_SIZE):
            batch = need_ai[i : i + BATCH_SIZE]

            if use_anthropic:
                categories = await self._categorize_batch_anthropic(batch, model=model or "claude-opus-4-20250514")
            else:
                categories = await self._categorize_batch_gemini(batch)

            for txn, category in zip(batch, categories):
                txn.ai_category = category if category in VALID_CATEGORIES else "Other"
                categorized_count += 1

            # Rate limiting only needed for Gemini free tier (10 RPM)
            if not use_anthropic and i + BATCH_SIZE < len(need_ai):
                await asyncio.sleep(6)

        await db.commit()
        return {"categorized": categorized_count, "total_uncategorized": total}

    async def _categorize_batch_gemini(self, transactions: list[Transaction]) -> list[str]:
        txn_list = _build_txn_list(transactions)
        prompt = _build_categorize_prompt(txn_list)

        try:
            response = await asyncio.to_thread(
                self.gemini_client.models.generate_content,
                model="gemini-2.5-flash",
                contents=prompt,
                config=types.GenerateContentConfig(
                    response_mime_type="application/json",
                    temperature=0.1,
                ),
            )

            parsed = json.loads(response.text)
            category_map = {item["id"]: item["category"] for item in parsed}
            return [category_map.get(idx, "Other") for idx in range(len(transactions))]

        except Exception as e:
            logger.error(f"Gemini categorization failed: {e}")
            return ["Other"] * len(transactions)

    async def _categorize_batch_anthropic(self, transactions: list[Transaction], model: str = "claude-opus-4-20250514") -> list[str]:
        txn_list = _build_txn_list(transactions)
        prompt = _build_categorize_prompt(txn_list)

        try:
            response = await self.anthropic_client.messages.create(
                model=model,
                max_tokens=2048,
                temperature=0.1,
                system="You are a transaction categorizer. Respond with ONLY valid JSON, no markdown fencing.",
                messages=[{"role": "user", "content": prompt}],
            )

            text = response.content[0].text.strip()
            # Strip markdown fences if present
            if text.startswith("```"):
                text = text.split("\n", 1)[1] if "\n" in text else text[3:]
                if text.endswith("```"):
                    text = text[:-3].strip()

            parsed = json.loads(text)
            category_map = {item["id"]: item["category"] for item in parsed}
            return [category_map.get(idx, "Other") for idx in range(len(transactions))]

        except Exception as e:
            logger.error(f"Anthropic categorization failed: {e}")
            return ["Other"] * len(transactions)


# Backward compatibility alias
GeminiCategorizer = TransactionCategorizer
