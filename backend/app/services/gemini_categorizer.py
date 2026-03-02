import asyncio
import json
import logging
import re
import uuid

import anthropic
from google import genai
from google.genai import types
from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.models.account import Account
from app.models.transaction import Transaction
from app.services.analytics_service import (
    CREDIT_CARD_PAYMENT_PATTERNS,
    normalize_category,
)

logger = logging.getLogger(__name__)


async def _get_merchant_rules(user_id: uuid.UUID, db: AsyncSession) -> dict[str, str]:
    """For each merchant, find the most recent user_category set by this user."""
    result = await db.execute(
        select(Transaction.merchant_name, Transaction.user_category, Transaction.date)
        .join(Account, Transaction.account_id == Account.id)
        .where(
            Account.user_id == user_id,
            Transaction.merchant_name.isnot(None),
            Transaction.merchant_name != "",
            Transaction.user_category.isnot(None),
        )
        .order_by(Transaction.date.desc())
    )
    rules: dict[str, str] = {}
    for row in result.all():
        if row.merchant_name not in rules:
            rules[row.merchant_name] = row.user_category
    return rules


def _is_cc_payment_desc(description: str) -> bool:
    """Check if a transaction description matches a known CC payment pattern."""
    desc_upper = description.upper()
    return any(p.upper() in desc_upper for p in CREDIT_CARD_PAYMENT_PATTERNS)

# Description/merchant keyword rules — checked BEFORE AI.
# Each tuple: (description_regex | None, merchant_regex | None, category)
KEYWORD_RULES: list[tuple[str | None, str | None, str]] = [
    # --- Zelle P2P: parse the "for ..." field ---
    (r"zelle.*for.*(sandra|cleaning|limpiez)", None, "Personal Care"),
    (r"zelle.*for.*(brazas|cheesecake|restaurant|olive garden|chick.?fil|mcdonald|chipotle|p\.?f\.?\s*chang)", None, "Restaurants"),
    (r"zelle.*for.*(starbucks|coffee|dunkin)", None, "Coffee & Drinks"),
    (r"zelle.*for.*(grocery|groceries|hmart|h\s*mart|trader|publix|whole\s*foods)", None, "Groceries"),
    (r"zelle.*for.*(rent|mortgage)", None, "Rent & Mortgage"),
    (r"zelle.*for.*(garbage|trash)", None, "Utilities"),
    # --- Merchant-pattern overrides (when Plaid gets it wrong) ---
    (None, r"geico|progressive|allstate|castle\s*key|state\s*farm", "Insurance"),
    (None, r"goodyear|jiffy\s*lube|autozone|pep\s*boys", "Transportation"),
    (None, r"masterclass", "Subscriptions"),
    (None, r"blizzard|riot|steam\s*games|nintendo|raidbots|restedxp|epic\s*games", "Entertainment"),
    (None, r"discord|netflix|spotify|youtube\s*premium|crunchyroll|viki|hulu|apple\s*music", "Subscriptions"),
    (None, r"apple\s*online\s*store|apple\.com/bill", "Shopping"),
    (None, r"target\.com|target\s+\d", "Shopping"),
    (None, r"planet\s*fitness|gym|la\s*fitness", "Personal Care"),
    (None, r"aidvantage", "Education"),
]


def _apply_keyword_rules(description: str, merchant: str | None) -> str | None:
    """Match description/merchant against keyword rules. Returns category or None."""
    desc_lower = (description or "").lower()
    merch_lower = (merchant or "").lower()
    for desc_pattern, merch_pattern, category in KEYWORD_RULES:
        if desc_pattern and re.search(desc_pattern, desc_lower):
            return category
        if merch_pattern and re.search(merch_pattern, merch_lower):
            return category
    return None


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

Important rules:
- For Zelle/Venmo/CashApp payments, look at the "for" field in the description to determine the actual purpose.
  Example: "Zelle payment to X for Cheesecake Factory" → Restaurants
  Example: "Zelle payment to X for Sandra cleaning" → Personal Care
  If there is no "for" field or the purpose is unclear, use "Other".
- For installment/financing payments (e.g. "MONTHLY INSTALLMENTS (X OF 12)"), categorize as Shopping (device purchase).
- Insurance payments (GEICO, Progressive, Allstate, Castle Key) → Insurance
- Auto repair/maintenance (Goodyear, Jiffy Lube) → Transportation
- Online learning platforms (MasterClass, Coursera, Udemy) → Subscriptions
- Gaming services (Blizzard, Riot, Steam, Nintendo, Epic Games) → Entertainment
- Streaming/digital subscriptions (Discord, Netflix, Spotify, YouTube Premium, Crunchyroll) → Subscriptions
- Student loan servicers (Aidvantage, Navient, Nelnet) → Education
- Avoid using "Other" unless no category fits at all.

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

        # Apply merchant rules from user's previous manual categorizations
        merchant_rules = await _get_merchant_rules(user_id, db)
        still_need_ai = []
        merchant_tagged = 0
        for txn in need_ai:
            if txn.merchant_name and txn.merchant_name in merchant_rules:
                txn.ai_category = merchant_rules[txn.merchant_name]
                merchant_tagged += 1
            else:
                still_need_ai.append(txn)
        categorized_count += merchant_tagged
        need_ai = still_need_ai

        # Apply description/merchant keyword rules
        after_keywords = []
        keyword_tagged = 0
        for txn in need_ai:
            kw_cat = _apply_keyword_rules(txn.description, txn.merchant_name)
            if kw_cat:
                txn.ai_category = kw_cat
                keyword_tagged += 1
            else:
                after_keywords.append(txn)
        categorized_count += keyword_tagged
        need_ai = after_keywords

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


    async def recategorize_all(
        self,
        user_id: uuid.UUID,
        db: AsyncSession,
        provider: str = "gemini",
        model: str | None = None,
    ) -> dict:
        """Re-evaluate ALL transactions (except user_category overrides).

        Applies keyword rules, merchant rules, and AI to transactions
        stuck in 'Other' or with bad/missing categories.
        Never touches user_category.
        """
        result = await db.execute(
            select(Transaction)
            .join(Account, Transaction.account_id == Account.id)
            .where(
                Account.user_id == user_id,
                or_(
                    Transaction.user_category.is_(None),
                    Transaction.user_category == "",
                ),
            )
        )
        transactions = result.scalars().all()

        if not transactions:
            return {"total_reviewed": 0, "updated": 0, "sent_to_ai": 0}

        updated = 0
        ai_needed = []
        merchant_rules = await _get_merchant_rules(user_id, db)

        for txn in transactions:
            # CC payments
            if _is_cc_payment_desc(txn.description):
                if txn.ai_category != "Payment":
                    txn.ai_category = "Payment"
                    updated += 1
                continue

            # Keyword rules
            kw_cat = _apply_keyword_rules(txn.description, txn.merchant_name)
            if kw_cat:
                if txn.ai_category != kw_cat:
                    txn.ai_category = kw_cat
                    updated += 1
                continue

            # Merchant rules
            if txn.merchant_name and txn.merchant_name in merchant_rules:
                rule_cat = merchant_rules[txn.merchant_name]
                if txn.ai_category != rule_cat:
                    txn.ai_category = rule_cat
                    updated += 1
                continue

            # Check if effective category is "Other", None, or a raw Plaid value
            effective = txn.category or txn.ai_category
            normalized = normalize_category(effective) if effective else None
            if normalized in ("Other", None, "Uncategorized"):
                ai_needed.append(txn)

        # Send remaining "Other"/uncategorized to AI
        use_anthropic = provider == "anthropic" and self.anthropic_client
        for i in range(0, len(ai_needed), BATCH_SIZE):
            batch = ai_needed[i : i + BATCH_SIZE]

            if use_anthropic:
                categories = await self._categorize_batch_anthropic(batch, model=model or "claude-opus-4-20250514")
            else:
                categories = await self._categorize_batch_gemini(batch)

            for txn, category in zip(batch, categories):
                new_cat = category if category in VALID_CATEGORIES else "Other"
                if new_cat != txn.ai_category:
                    txn.ai_category = new_cat
                    updated += 1

            if not use_anthropic and i + BATCH_SIZE < len(ai_needed):
                await asyncio.sleep(6)

        await db.commit()
        return {
            "total_reviewed": len(transactions),
            "updated": updated,
            "sent_to_ai": len(ai_needed),
        }


# Backward compatibility alias
GeminiCategorizer = TransactionCategorizer
