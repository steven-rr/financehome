import asyncio
import json
import logging
import uuid

from google import genai
from google.genai import types
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.models.account import Account
from app.models.transaction import Transaction

logger = logging.getLogger(__name__)

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


class GeminiCategorizer:
    def __init__(self):
        self.client = genai.Client(api_key=settings.gemini_api_key)

    async def categorize_uncategorized(
        self,
        user_id: uuid.UUID,
        db: AsyncSession,
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

        categorized_count = 0
        total = len(transactions)

        for i in range(0, total, BATCH_SIZE):
            batch = transactions[i : i + BATCH_SIZE]
            categories = await self._categorize_batch(batch)

            for txn, category in zip(batch, categories):
                txn.ai_category = category if category in VALID_CATEGORIES else "Other"
                categorized_count += 1

            # Respect 10 RPM free tier limit
            if i + BATCH_SIZE < total:
                await asyncio.sleep(6)

        await db.commit()
        return {"categorized": categorized_count, "total_uncategorized": total}

    async def _categorize_batch(self, transactions: list[Transaction]) -> list[str]:
        """Send a batch of transactions to Gemini and get back category assignments."""
        txn_list = []
        for idx, txn in enumerate(transactions):
            txn_list.append({
                "id": idx,
                "description": txn.description,
                "merchant": txn.merchant_name or "",
                "amount": float(txn.amount),
            })

        prompt = f"""Categorize each transaction into exactly one of these categories:
{json.dumps(VALID_CATEGORIES)}

Transactions:
{json.dumps(txn_list)}

Respond with ONLY a JSON array of objects, one per transaction, in the same order.
Each object must have "id" (the index) and "category" (one of the valid categories above).
Example: [{{"id": 0, "category": "Groceries"}}, {{"id": 1, "category": "Restaurants"}}]"""

        try:
            response = await asyncio.to_thread(
                self.client.models.generate_content,
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
