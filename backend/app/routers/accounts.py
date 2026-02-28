import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.database import get_db
from app.models.account import Account
from app.models.transaction import Transaction
from app.models.user import User
from app.routers.auth import get_current_user
from app.services.sync_service import SyncService

router = APIRouter()


class AccountResponse(BaseModel):
    id: uuid.UUID
    plaid_account_id: str
    name: str
    official_name: str | None
    type: str
    subtype: str | None
    balance_current: float | None
    balance_available: float | None
    balance_manual: float | None = None
    balance_manual_updated_at: str | None = None
    balance_effective: float | None = None
    currency: str
    institution_name: str | None = None
    data_source: str = "plaid"
    last_synced: str | None = None
    latest_transaction_date: str | None = None
    display_name: str | None = None
    is_hidden: bool = False

    model_config = {"from_attributes": True}


class AccountUpdate(BaseModel):
    balance_manual: float | None = None
    display_name: str | None = None
    is_hidden: bool | None = None


def _build_account_response(
    acct: Account, latest_txn_date=None, txn_delta: float | None = None,
) -> AccountResponse:
    is_manual = acct.plaid_account_id.startswith("manual-")

    # data_source reflects where the account came from, not how balance was set
    source = "csv" if is_manual else "plaid"

    # Determine effective balance
    # For accounts with a manual anchor: anchor + delta from transactions after anchor date
    if acct.balance_manual is not None:
        if is_manual:
            balance_effective = acct.balance_manual + (txn_delta or 0)
        elif acct.balance_manual_updated_at and acct.last_synced:
            if acct.balance_manual_updated_at > acct.last_synced:
                balance_effective = acct.balance_manual + (txn_delta or 0)
            else:
                balance_effective = acct.balance_current
        else:
            balance_effective = acct.balance_manual + (txn_delta or 0)
    elif acct.balance_current is not None:
        balance_effective = acct.balance_current
    else:
        balance_effective = None

    return AccountResponse(
        id=acct.id,
        plaid_account_id=acct.plaid_account_id,
        name=acct.name,
        official_name=acct.official_name,
        type=acct.type,
        subtype=acct.subtype,
        balance_current=acct.balance_current,
        balance_available=acct.balance_available,
        balance_manual=acct.balance_manual,
        balance_manual_updated_at=(
            acct.balance_manual_updated_at.isoformat() if acct.balance_manual_updated_at else None
        ),
        balance_effective=round(balance_effective, 2) if balance_effective is not None else None,
        currency=acct.currency,
        institution_name=acct.plaid_link.institution_name if acct.plaid_link else None,
        data_source=source,
        last_synced=acct.last_synced.isoformat() if acct.last_synced else None,
        latest_transaction_date=str(latest_txn_date) if latest_txn_date else None,
        display_name=acct.display_name,
        is_hidden=acct.is_hidden,
    )


@router.get("", response_model=list[AccountResponse])
async def list_accounts(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    include_hidden: bool = Query(False),
):
    query = (
        select(Account)
        .options(selectinload(Account.plaid_link))
        .where(Account.user_id == current_user.id)
    )
    if not include_hidden:
        query = query.where(Account.is_hidden == False)  # noqa: E712
    query = query.order_by(Account.name)

    result = await db.execute(query)
    accounts = result.scalars().all()

    # Batch-query latest transaction dates
    if accounts:
        account_ids = [a.id for a in accounts]
        txn_stats = await db.execute(
            select(
                Transaction.account_id,
                func.max(Transaction.date).label("latest_date"),
            )
            .where(Transaction.account_id.in_(account_ids))
            .group_by(Transaction.account_id)
        )
        latest_dates = {row.account_id: row.latest_date for row in txn_stats.all()}
    else:
        latest_dates = {}

    # For accounts with a manual balance anchor, compute transaction delta
    # (sum of transactions after the anchor date)
    anchored_ids = [
        a for a in accounts
        if a.balance_manual is not None and a.balance_manual_updated_at is not None
    ]
    txn_deltas: dict[uuid.UUID, float] = {}
    if anchored_ids:
        for acct in anchored_ids:
            anchor_date = acct.balance_manual_updated_at.date()
            delta_result = await db.execute(
                select(func.coalesce(func.sum(Transaction.amount), 0))
                .where(
                    Transaction.account_id == acct.id,
                    Transaction.date > anchor_date,
                )
            )
            txn_deltas[acct.id] = delta_result.scalar() or 0

    return [
        _build_account_response(acct, latest_dates.get(acct.id), txn_deltas.get(acct.id))
        for acct in accounts
    ]


@router.get("/{account_id}", response_model=AccountResponse)
async def get_account(
    account_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(Account)
        .options(selectinload(Account.plaid_link))
        .where(Account.id == account_id, Account.user_id == current_user.id)
    )
    account = result.scalar_one_or_none()
    if not account:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Account not found")
    return _build_account_response(account)


@router.patch("/{account_id}", response_model=AccountResponse)
async def update_account(
    account_id: uuid.UUID,
    body: AccountUpdate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(Account)
        .options(selectinload(Account.plaid_link))
        .where(Account.id == account_id, Account.user_id == current_user.id)
    )
    account = result.scalar_one_or_none()
    if not account:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Account not found")

    update_data = body.model_dump(exclude_unset=True)
    for field, value in update_data.items():
        setattr(account, field, value)

    if "balance_manual" in update_data:
        account.balance_manual_updated_at = datetime.now(timezone.utc)

    await db.commit()
    await db.refresh(account)
    return _build_account_response(account)


@router.post("/sync", status_code=status.HTTP_200_OK)
async def sync_all_accounts(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    sync_service = SyncService()
    synced = await sync_service.sync_all_for_user(user_id=current_user.id, db=db)
    return {"synced_accounts": synced}
