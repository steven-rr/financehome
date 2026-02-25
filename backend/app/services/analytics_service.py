import uuid
from datetime import date

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.account import Account
from app.models.transaction import Transaction


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
