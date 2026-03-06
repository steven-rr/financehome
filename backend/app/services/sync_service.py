import logging
import uuid
from datetime import date, datetime, timezone

from plaid.model.transactions_sync_request import TransactionsSyncRequest
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.account import Account
from app.models.budget import Budget
from app.models.notification_preference import NotificationPreference
from app.models.plaid_link import PlaidLink
from app.models.transaction import Transaction
from app.models.user import User
from app.services.analytics_service import effective_category_expr, normalize_category
from app.services.plaid_service import PlaidService
from app.utils.encryption import decrypt_token

logger = logging.getLogger(__name__)


class SyncService:
    def __init__(self):
        self.plaid = PlaidService()

    async def sync_all_for_user(self, user_id: uuid.UUID, db: AsyncSession) -> int:
        result = await db.execute(
            select(PlaidLink).where(PlaidLink.user_id == user_id, PlaidLink.status == "active")
        )
        links = result.scalars().all()

        synced = 0
        for link in links:
            if link.access_token.startswith("manual-") or link.access_token.startswith("demo-"):
                continue
            await self._sync_link(link, db)
            synced += 1

        return synced

    async def sync_by_item_id(self, item_id: str, db: AsyncSession) -> None:
        result = await db.execute(select(PlaidLink).where(PlaidLink.item_id == item_id))
        link = result.scalar_one_or_none()
        if link:
            await self._sync_link(link, db)

    async def _sync_link(self, link: PlaidLink, db: AsyncSession) -> None:
        access_token = decrypt_token(link.access_token)
        cursor = link.sync_cursor
        has_more = True

        while has_more:
            request_params = {"access_token": access_token}
            if cursor:
                request_params["cursor"] = cursor

            request = TransactionsSyncRequest(**request_params)
            response = self.plaid.client.transactions_sync(request)

            # Handle added transactions
            for txn in response.added:
                await self._upsert_transaction(txn, link, db)

            # Handle modified transactions
            for txn in response.modified:
                await self._upsert_transaction(txn, link, db)

            # Handle removed transactions
            for removed_txn in response.removed:
                result = await db.execute(
                    select(Transaction).where(
                        Transaction.plaid_transaction_id == removed_txn.transaction_id
                    )
                )
                existing = result.scalar_one_or_none()
                if existing:
                    await db.delete(existing)

            cursor = response.next_cursor
            has_more = response.has_more

        # Update cursor and sync timestamps
        link.sync_cursor = cursor
        await self._update_account_balances(access_token, link, db)
        await db.commit()

    async def _upsert_transaction(self, txn, link: PlaidLink, db: AsyncSession) -> None:
        result = await db.execute(
            select(Transaction).where(Transaction.plaid_transaction_id == txn.transaction_id)
        )
        existing = result.scalar_one_or_none()

        # Find the matching account
        acct_result = await db.execute(
            select(Account).where(
                Account.plaid_account_id == txn.account_id,
                Account.plaid_link_id == link.id,
            )
        )
        account = acct_result.scalar_one_or_none()
        if not account:
            return

        category = None
        if txn.personal_finance_category:
            category = normalize_category(txn.personal_finance_category.primary)

        if existing:
            existing.amount = txn.amount
            existing.merchant_name = txn.merchant_name
            existing.description = txn.name
            existing.category = category
            existing.is_pending = txn.pending
            existing.date = txn.date
        else:
            new_txn = Transaction(
                account_id=account.id,
                plaid_transaction_id=txn.transaction_id,
                date=txn.date,
                amount=txn.amount,
                merchant_name=txn.merchant_name,
                description=txn.name,
                category=category,
                subcategory=txn.personal_finance_category.detailed if txn.personal_finance_category else None,
                is_pending=txn.pending,
            )
            db.add(new_txn)
            # Fire-and-forget alert checks for new transactions
            try:
                await self._check_alerts(new_txn, link.user_id, db)
            except Exception:
                logger.exception("Alert check failed for transaction %s", txn.transaction_id)

    async def _check_alerts(self, txn: Transaction, user_id: uuid.UUID, db: AsyncSession) -> None:
        # Only alert on expenses (positive amounts in Plaid convention)
        if txn.amount <= 0:
            return

        result = await db.execute(
            select(NotificationPreference).where(NotificationPreference.user_id == user_id)
        )
        prefs = result.scalar_one_or_none()
        if not prefs:
            return

        user_result = await db.execute(select(User).where(User.id == user_id))
        user = user_result.scalar_one_or_none()
        if not user:
            return

        # Lazy import to avoid circular dependency
        from app.services.email_service import EmailService
        email_service = EmailService()

        # Large transaction alert
        if prefs.alert_large_transaction and txn.amount >= prefs.alert_large_transaction_threshold:
            merchant = txn.merchant_name or txn.description or "Unknown"
            await email_service.send_large_transaction_alert(
                to=user.email,
                amount=txn.amount,
                merchant=merchant[:40],
                txn_date=str(txn.date),
            )

        # Budget exceeded alert
        effective_cat = txn.user_category or txn.category or txn.ai_category
        if prefs.alert_budget_exceeded and effective_cat:
            budget_result = await db.execute(
                select(Budget).where(
                    Budget.user_id == user_id,
                    Budget.category == effective_cat,
                )
            )
            budget = budget_result.scalar_one_or_none()
            if budget:
                # Sum this month's spending in this category
                month_start = date.today().replace(day=1)
                cat_expr = effective_category_expr()
                spend_result = await db.execute(
                    select(func.coalesce(func.sum(Transaction.amount), 0.0))
                    .join(Account, Transaction.account_id == Account.id)
                    .where(
                        Account.user_id == user_id,
                        Transaction.amount > 0,
                        Transaction.date >= month_start,
                        cat_expr == effective_cat,
                    )
                )
                month_total = float(spend_result.scalar())
                if month_total > budget.monthly_limit:
                    await email_service.send_budget_alert(
                        to=user.email,
                        category=effective_cat,
                        limit=budget.monthly_limit,
                        actual=month_total,
                    )

    async def _update_account_balances(
        self, access_token: str, link: PlaidLink, db: AsyncSession
    ) -> None:
        response = self.plaid.client.accounts_get({"access_token": access_token})
        now = datetime.now(timezone.utc)

        for acct_data in response.accounts:
            result = await db.execute(
                select(Account).where(
                    Account.plaid_account_id == acct_data.account_id,
                    Account.plaid_link_id == link.id,
                )
            )
            account = result.scalar_one_or_none()
            if account:
                account.balance_current = acct_data.balances.current
                account.balance_available = acct_data.balances.available
                account.last_synced = now
