import uuid

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.database import get_db
from app.models.account import Account
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
    currency: str
    institution_name: str | None = None

    model_config = {"from_attributes": True}


@router.get("", response_model=list[AccountResponse])
async def list_accounts(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(Account)
        .options(selectinload(Account.plaid_link))
        .where(Account.user_id == current_user.id)
        .order_by(Account.name)
    )
    accounts = result.scalars().all()

    response = []
    for acct in accounts:
        data = AccountResponse.model_validate(acct)
        if acct.plaid_link:
            data.institution_name = acct.plaid_link.institution_name
        response.append(data)
    return response


@router.get("/{account_id}", response_model=AccountResponse)
async def get_account(
    account_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(Account).where(Account.id == account_id, Account.user_id == current_user.id)
    )
    account = result.scalar_one_or_none()
    if not account:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Account not found")
    return AccountResponse.model_validate(account)


@router.post("/sync", status_code=status.HTTP_200_OK)
async def sync_all_accounts(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    sync_service = SyncService()
    synced = await sync_service.sync_all_for_user(user_id=current_user.id, db=db)
    return {"synced_accounts": synced}
