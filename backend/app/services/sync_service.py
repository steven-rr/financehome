import uuid
from datetime import datetime, timezone

from plaid.model.transactions_sync_request import TransactionsSyncRequest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.account import Account
from app.models.plaid_link import PlaidLink
from app.models.transaction import Transaction
from app.services.plaid_service import PlaidService
from app.utils.encryption import decrypt_token


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
            category = txn.personal_finance_category.primary

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
