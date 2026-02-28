import statistics
import uuid
from dataclasses import dataclass
from datetime import date, timedelta

from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.account import Account
from app.models.transaction import Transaction
from app.services.analytics_service import (
    TRANSFER_CATEGORIES,
    _is_cc_payment,
    effective_category_expr,
    normalize_category,
)

# Frequency windows: (label, min_days, max_days, monthly_multiplier)
# Recurring-specific categories based on merchant keywords
RECURRING_CATEGORIES = [
    ("Streaming", [
        "netflix", "spotify", "hulu", "disney", "hbo", "max", "apple tv",
        "youtube", "peacock", "paramount", "crunchyroll", "audible", "tidal",
    ]),
    ("Software & Apps", [
        "icloud", "adobe", "microsoft", "dropbox", "google one", "openai",
        "chatgpt", "notion", "slack", "zoom", "github", "1password",
        "lastpass", "grammarly", "canva",
    ]),
    ("Fitness", [
        "planet fitness", "gym", "fitness", "peloton", "crossfit", "ymca",
        "orangetheory", "equinox",
    ]),
    ("Insurance", [
        "insurance", "geico", "state farm", "progressive", "allstate",
        "liberty mutual", "usaa",
    ]),
    ("Phone & Internet", [
        "verizon", "t-mobile", "at&t", "comcast", "xfinity", "spectrum",
        "cox", "mint mobile", "google fi", "visible",
    ]),
    ("Utilities", [
        "electric", "water", "gas", "power", "energy", "utility", "sewage",
    ]),
    ("Memberships", [
        "amazon prime", "costco", "sam's club", "bj's", "aaa",
    ]),
    ("Storage", [
        "public storage", "extra space", "u-haul", "cubesmart",
    ]),
    ("News & Media", [
        "new york times", "nytimes", "washington post", "wall street journal",
        "wsj", "apple news", "medium", "substack",
    ]),
]


def _classify_recurring(merchant: str) -> str | None:
    """Match a merchant name to a recurring-specific category."""
    lower = merchant.lower()
    for category, keywords in RECURRING_CATEGORIES:
        if any(kw in lower for kw in keywords):
            return category
    return None


FREQUENCY_BANDS = [
    ("weekly", 5, 9, 4.33),
    ("bi-weekly", 12, 17, 2.17),
    ("monthly", 26, 35, 1.0),
    ("quarterly", 80, 100, 0.33),
    ("annual", 340, 390, 0.083),
]


@dataclass
class RecurringItem:
    merchant: str
    amount: float
    frequency: str
    category: str
    confidence: float
    last_date: date
    occurrence_count: int


class RecurringService:
    async def detect_recurring(
        self, user_id: uuid.UUID, db: AsyncSession
    ) -> dict:
        effective_category = effective_category_expr()
        cutoff = date.today() - timedelta(days=548)  # ~18 months

        result = await db.execute(
            select(
                Transaction.merchant_name,
                Transaction.description,
                Transaction.amount,
                Transaction.date,
                effective_category.label("effective_category"),
            )
            .join(Account, Transaction.account_id == Account.id)
            .where(
                Account.user_id == user_id,
                Transaction.is_pending == False,  # noqa: E712
                Transaction.amount > 0,
                Transaction.date >= cutoff,
                or_(
                    effective_category.is_(None),
                    effective_category.notin_(TRANSFER_CATEGORIES),
                ),
                ~_is_cc_payment(),
            )
            .order_by(Transaction.date)
        )
        rows = result.all()

        # Group by merchant_name (fall back to description)
        groups: dict[str, list] = {}
        for row in rows:
            key = (row.merchant_name or row.description).strip().lower()
            groups.setdefault(key, []).append(row)

        # Analyze each group
        today = date.today()
        items: list[RecurringItem] = []
        for txns in groups.values():
            if len(txns) < 3:
                continue
            item = self._analyze_group(txns)
            if item and item.confidence >= 0.6:
                # Skip if last charge was more than 2x the expected interval ago (likely canceled)
                max_gap = self._max_expected_gap(item.frequency)
                if (today - item.last_date).days > max_gap:
                    continue
                items.append(item)

        items.sort(key=lambda i: i.amount, reverse=True)
        total_monthly = sum(
            i.amount * self._monthly_multiplier(i.frequency) for i in items
        )

        return {
            "total_monthly_cost": round(total_monthly, 2),
            "items": [
                {
                    "merchant": i.merchant,
                    "amount": round(i.amount, 2),
                    "frequency": i.frequency,
                    "category": i.category,
                    "confidence": round(i.confidence, 2),
                    "last_date": i.last_date.isoformat(),
                    "occurrence_count": i.occurrence_count,
                }
                for i in items
            ],
        }

    def _analyze_group(self, txns: list) -> RecurringItem | None:
        dates = sorted(t.date for t in txns)
        amounts = [t.amount for t in txns]

        intervals = [
            (dates[i + 1] - dates[i]).days for i in range(len(dates) - 1)
        ]
        if not intervals:
            return None

        median_interval = statistics.median(intervals)

        # Match to known frequency band
        frequency = None
        for label, min_d, max_d, _ in FREQUENCY_BANDS:
            if min_d <= median_interval <= max_d:
                frequency = label
                break
        if not frequency:
            return None

        # Interval regularity score
        if median_interval > 0:
            interval_deviations = [
                abs(iv - median_interval) / median_interval for iv in intervals
            ]
            interval_score = 1.0 - min(statistics.mean(interval_deviations), 1.0)
        else:
            interval_score = 0.0

        # Amount consistency score (coefficient of variation)
        mean_amount = statistics.mean(amounts)
        if mean_amount > 0 and len(amounts) >= 2:
            cv = statistics.stdev(amounts) / mean_amount
            amount_score = 1.0 - min(cv, 1.0)
        else:
            amount_score = 0.5

        confidence = (interval_score * 0.65) + (amount_score * 0.35)

        latest = max(txns, key=lambda t: t.date)
        merchant_display = latest.merchant_name or latest.description
        # Use recurring-specific category if matched, otherwise fall back to transaction category
        category = _classify_recurring(merchant_display) or normalize_category(
            latest.effective_category or "Uncategorized"
        )

        return RecurringItem(
            merchant=merchant_display,
            amount=statistics.median(amounts),
            frequency=frequency,
            category=category,
            confidence=confidence,
            last_date=latest.date,
            occurrence_count=len(txns),
        )

    def _monthly_multiplier(self, frequency: str) -> float:
        for label, _, _, mult in FREQUENCY_BANDS:
            if label == frequency:
                return mult
        return 1.0

    def _max_expected_gap(self, frequency: str) -> int:
        """Max days since last charge before considering it canceled (2x the upper bound)."""
        for label, _, max_d, _ in FREQUENCY_BANDS:
            if label == frequency:
                return max_d * 2
        return 70  # default ~2 months
