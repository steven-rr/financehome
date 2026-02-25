import uuid

import plaid
from plaid.api import plaid_api
from plaid.model.country_code import CountryCode
from plaid.model.item_public_token_exchange_request import ItemPublicTokenExchangeRequest
from plaid.model.link_token_create_request import LinkTokenCreateRequest
from plaid.model.link_token_create_request_user import LinkTokenCreateRequestUser
from plaid.model.products import Products
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.models.account import Account
from app.models.plaid_link import PlaidLink
from app.utils.encryption import encrypt_token

PLAID_ENV_MAP = {
    "sandbox": plaid.Environment.Sandbox,
    "development": plaid.Environment.Development,
    "production": plaid.Environment.Production,
}


class PlaidService:
    def __init__(self):
        configuration = plaid.Configuration(
            host=PLAID_ENV_MAP.get(settings.plaid_env, plaid.Environment.Sandbox),
            api_key={
                "clientId": settings.plaid_client_id,
                "secret": settings.plaid_secret,
            },
        )
        api_client = plaid.ApiClient(configuration)
        self.client = plaid_api.PlaidApi(api_client)

    async def create_link_token(self, user_id: str) -> str:
        request = LinkTokenCreateRequest(
            user=LinkTokenCreateRequestUser(client_user_id=user_id),
            client_name="FinanceHome",
            products=[Products("transactions")],
            country_codes=[CountryCode("US")],
            language="en",
        )
        if settings.plaid_webhook_url:
            request.webhook = settings.plaid_webhook_url

        response = self.client.link_token_create(request)
        return response.link_token

    async def exchange_and_store(
        self,
        public_token: str,
        user_id: uuid.UUID,
        db: AsyncSession,
    ) -> dict:
        # Exchange public token for access token
        exchange_request = ItemPublicTokenExchangeRequest(public_token=public_token)
        exchange_response = self.client.item_public_token_exchange(exchange_request)

        access_token = exchange_response.access_token
        item_id = exchange_response.item_id

        # Get institution info
        item_response = self.client.item_get({"access_token": access_token})
        institution_id = item_response.item.institution_id

        institution_name = "Unknown"
        if institution_id:
            inst_response = self.client.institutions_get_by_id(
                {"institution_id": institution_id, "country_codes": ["US"]}
            )
            institution_name = inst_response.institution.name

        # Store encrypted access token
        plaid_link = PlaidLink(
            user_id=user_id,
            access_token=encrypt_token(access_token),
            item_id=item_id,
            institution_name=institution_name,
        )
        db.add(plaid_link)
        await db.flush()

        # Fetch and store accounts
        accounts_response = self.client.accounts_get({"access_token": access_token})
        accounts_linked = 0

        for acct in accounts_response.accounts:
            account = Account(
                user_id=user_id,
                plaid_link_id=plaid_link.id,
                plaid_account_id=acct.account_id,
                name=acct.name,
                official_name=acct.official_name,
                type=acct.type.value,
                subtype=acct.subtype.value if acct.subtype else None,
                balance_current=acct.balances.current,
                balance_available=acct.balances.available,
                currency=acct.balances.iso_currency_code or "USD",
            )
            db.add(account)
            accounts_linked += 1

        await db.commit()

        return {
            "institution_name": institution_name,
            "accounts_linked": accounts_linked,
        }
