import uuid
from datetime import date

from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.account import Account
from app.models.transaction import Transaction


# Categories that are never real spending (just moving money between accounts)
TRANSFER_CATEGORIES = {
    "LOAN_DISBURSEMENTS", "TRANSFER_IN",
    "Payment", "Credit", "Pago/crédito",
}

# Descriptions that indicate credit card payments (double-counted from checking)
CREDIT_CARD_PAYMENT_PATTERNS = [
    "APPLECARD", "APPLE CARD", "CHASE CREDIT CRD", "CAPITAL ONE DES:",
]


def _is_cc_payment():
    """SQLAlchemy filter that matches credit card payment descriptions."""
    return or_(
        *[Transaction.description.ilike(f"%{p}%") for p in CREDIT_CARD_PAYMENT_PATTERNS]
    )


class AnalyticsService:
    async def get_spending_by_category(
        self,
        user_id: uuid.UUID,
        start_date: date,
        end_date: date,
        db: AsyncSession,
    ) -> list[dict]:
        result = await db.execute(
            select(
                Transaction.category,
                func.sum(Transaction.amount).label("total"),
                func.count().label("count"),
            )
            .join(Account, Transaction.account_id == Account.id)
            .where(
                Account.user_id == user_id,
                Transaction.date >= start_date,
                Transaction.date <= end_date,
                Transaction.amount > 0,
                Transaction.category.notin_(TRANSFER_CATEGORIES),
                ~_is_cc_payment(),
            )
            .group_by(Transaction.category)
            .order_by(func.sum(Transaction.amount).desc())
        )
        return [
            {"category": row.category or "Uncategorized", "total": round(row.total, 2), "count": row.count}
            for row in result.all()
        ]

    async def get_income_vs_expenses(
        self,
        user_id: uuid.UUID,
        start_date: date,
        end_date: date,
        db: AsyncSession,
    ) -> dict:
        result = await db.execute(
            select(func.sum(Transaction.amount))
            .join(Account, Transaction.account_id == Account.id)
            .where(
                Account.user_id == user_id,
                Transaction.date >= start_date,
                Transaction.date <= end_date,
            )
        )
        # In Plaid: positive = money out (expenses), negative = money in (income)
        all_txns = await db.execute(
            select(Transaction.amount)
            .join(Account, Transaction.account_id == Account.id)
            .where(
                Account.user_id == user_id,
                Transaction.date >= start_date,
                Transaction.date <= end_date,
                Transaction.category.notin_(TRANSFER_CATEGORIES),
                ~_is_cc_payment(),
            )
        )
        amounts = [row[0] for row in all_txns.all()]
        expenses = sum(a for a in amounts if a > 0)
        income = abs(sum(a for a in amounts if a < 0))

        return {
            "income": round(income, 2),
            "expenses": round(expenses, 2),
            "net": round(income - expenses, 2),
        }

    async def get_transactions_for_period(
        self,
        user_id: uuid.UUID,
        start_date: date,
        end_date: date,
        db: AsyncSession,
    ) -> list[dict]:
        result = await db.execute(
            select(Transaction)
            .join(Account, Transaction.account_id == Account.id)
            .where(
                Account.user_id == user_id,
                Transaction.date >= start_date,
                Transaction.date <= end_date,
            )
            .order_by(Transaction.date.desc())
        )
        transactions = result.scalars().all()
        return [
            {
                "date": str(t.date),
                "amount": t.amount,
                "merchant": t.merchant_name,
                "description": t.description,
                "category": t.category or "Uncategorized",
            }
            for t in transactions
        ]

    async def get_net_worth(self, user_id: uuid.UUID, db: AsyncSession) -> dict:
        result = await db.execute(
            select(Account).where(Account.user_id == user_id)
        )
        accounts = result.scalars().all()

        assets = 0.0
        liabilities = 0.0
        for acct in accounts:
            balance = acct.balance_current or 0
            if acct.type in ("depository", "investment"):
                assets += balance
            elif acct.type in ("credit", "loan"):
                liabilities += abs(balance)

        return {
            "assets": round(assets, 2),
            "liabilities": round(liabilities, 2),
            "net_worth": round(assets - liabilities, 2),
        }
