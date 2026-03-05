from fastapi import APIRouter, Depends, HTTPException, Request, status
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.models.user import User
from app.rate_limit import limiter
from app.routers.auth import get_current_user
from app.services.audit import log_event
from app.services.plaid_service import PlaidService

router = APIRouter()


class LinkTokenResponse(BaseModel):
    link_token: str


class ExchangeTokenRequest(BaseModel):
    public_token: str


class ExchangeTokenResponse(BaseModel):
    institution_name: str
    accounts_linked: int


@router.post("/link-token", response_model=LinkTokenResponse)
@limiter.limit("10/minute")
async def create_link_token(
    request: Request,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    plaid_service = PlaidService()
    link_token = await plaid_service.create_link_token(str(current_user.id))
    await log_event(db, "PLAID_LINK_CREATED", request, user_id=current_user.id)
    return LinkTokenResponse(link_token=link_token)


@router.post("/exchange-token", response_model=ExchangeTokenResponse)
@limiter.limit("5/minute")
async def exchange_public_token(
    request: Request,
    body: ExchangeTokenRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    plaid_service = PlaidService()
    result = await plaid_service.exchange_and_store(
        public_token=body.public_token,
        user_id=current_user.id,
        db=db,
    )
    await log_event(db, "PLAID_ACCOUNT_LINKED", request, user_id=current_user.id, details={
        "institution": result["institution_name"],
        "accounts_linked": result["accounts_linked"],
    })
    return ExchangeTokenResponse(
        institution_name=result["institution_name"],
        accounts_linked=result["accounts_linked"],
    )


@router.post("/webhook")
@limiter.limit("20/minute")
async def plaid_webhook(request: Request, db: AsyncSession = Depends(get_db)):
    body = await request.json()
    webhook_type = body.get("webhook_type")
    webhook_code = body.get("webhook_code")
    item_id = body.get("item_id")

    if webhook_type == "TRANSACTIONS":
        from app.services.sync_service import SyncService

        sync_service = SyncService()
        await sync_service.sync_by_item_id(item_id=item_id, db=db)

    return {"received": True}
