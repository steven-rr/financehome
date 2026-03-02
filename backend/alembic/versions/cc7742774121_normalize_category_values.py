"""normalize_category_values

Revision ID: cc7742774121
Revises: c0530379f594
Create Date: 2026-03-01 23:25:35.396047

"""
from typing import Sequence, Union

from alembic import op


# revision identifiers, used by Alembic.
revision: str = 'cc7742774121'
down_revision: Union[str, None] = 'c0530379f594'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

# Raw Plaid/CSV category values → normalized display names
NORMALIZATION_MAP = {
    "FOOD_AND_DRINK": "Restaurants",
    "Food & Drink": "Restaurants",
    "ENTERTAINMENT": "Entertainment",
    "GENERAL_MERCHANDISE": "Shopping",
    "GENERAL_SERVICES": "Other",
    "RENT_AND_UTILITIES": "Rent & Mortgage",
    "BANK_FEES": "Fees & Charges",
    "Grocery": "Groceries",
    "Gas": "Gas & Fuel",
    "Bills & Utilities": "Utilities",
    "Fees & Adjustments": "Fees & Charges",
    "Automotive": "Transportation",
    "Medical": "Healthcare",
    "Health": "Healthcare",
    "Personal": "Personal Care",
    "Home": "Rent & Mortgage",
    "Debit": "Other",
    "Interest": "Fees & Charges",
    "Installment": "Shopping",
    "Professional Services": "Other",
    "TRANSFER_OUT": "Transfer Out",
    "LOAN_PAYMENTS": "Loan Payments",
    "INCOME": "Income",
}


def upgrade() -> None:
    # 1. Normalize raw Plaid values in the `category` column
    for raw_value, normalized in NORMALIZATION_MAP.items():
        if raw_value != normalized:
            op.execute(
                f"UPDATE transactions SET category = '{normalized}' "
                f"WHERE category = '{raw_value}'"
            )

    # 2. Normalize any raw values that leaked into ai_category
    for raw_value, normalized in NORMALIZATION_MAP.items():
        if raw_value != normalized:
            op.execute(
                f"UPDATE transactions SET ai_category = '{normalized}' "
                f"WHERE ai_category = '{raw_value}'"
            )

    # 3. Fix specific merchant miscategorizations via ai_category
    #    (only where user hasn't manually categorized)

    # GEICO → Insurance
    op.execute(
        "UPDATE transactions SET ai_category = 'Insurance' "
        "WHERE (description ILIKE '%geico%' OR merchant_name ILIKE '%geico%' "
        "OR merchant_name ILIKE '%castle key%') "
        "AND (user_category IS NULL OR user_category = '')"
    )

    # Goodyear → Transportation
    op.execute(
        "UPDATE transactions SET ai_category = 'Transportation' "
        "WHERE (description ILIKE '%goodyear%' OR merchant_name ILIKE '%goodyear%') "
        "AND (user_category IS NULL OR user_category = '')"
    )

    # MasterClass → Subscriptions
    op.execute(
        "UPDATE transactions SET ai_category = 'Subscriptions' "
        "WHERE (description ILIKE '%masterclass%' OR merchant_name ILIKE '%masterclass%') "
        "AND (user_category IS NULL OR user_category = '')"
    )

    # Blizzard / Riot / Steam / Nintendo / Raidbots / RestedXP → Entertainment
    op.execute(
        "UPDATE transactions SET ai_category = 'Entertainment' "
        "WHERE (description ILIKE '%blizzard%' OR merchant_name ILIKE '%blizzard%' "
        "OR description ILIKE '%riot%' OR merchant_name ILIKE '%riot%' "
        "OR merchant_name ILIKE '%steam games%' "
        "OR merchant_name ILIKE '%nintendo%' "
        "OR merchant_name ILIKE '%raidbots%' "
        "OR merchant_name ILIKE '%restedxp%') "
        "AND (user_category IS NULL OR user_category = '')"
    )

    # Discord → Subscriptions
    op.execute(
        "UPDATE transactions SET ai_category = 'Subscriptions' "
        "WHERE (description ILIKE '%discord%' OR merchant_name ILIKE '%discord%') "
        "AND (user_category IS NULL OR user_category = '')"
    )

    # Apple Online Store → Shopping (but NOT Apple Card payments)
    op.execute(
        "UPDATE transactions SET ai_category = 'Shopping' "
        "WHERE (merchant_name ILIKE '%apple online store%' "
        "OR merchant_name ILIKE '%apple store%') "
        "AND description NOT ILIKE '%APPLECARD%' "
        "AND description NOT ILIKE '%APPLE CARD%' "
        "AND (user_category IS NULL OR user_category = '')"
    )

    # target.com → Shopping
    op.execute(
        "UPDATE transactions SET ai_category = 'Shopping' "
        "WHERE (description ILIKE '%target.com%' OR merchant_name ILIKE '%target.com%') "
        "AND (user_category IS NULL OR user_category = '')"
    )

    # Aidvantage (student loans) → Education
    op.execute(
        "UPDATE transactions SET ai_category = 'Education' "
        "WHERE (description ILIKE '%aidvantage%' OR merchant_name ILIKE '%aidvantage%') "
        "AND (user_category IS NULL OR user_category = '')"
    )

    # Planet Fitness → Personal Care
    op.execute(
        "UPDATE transactions SET ai_category = 'Personal Care' "
        "WHERE (description ILIKE '%planet fitness%' OR merchant_name ILIKE '%planet fitness%') "
        "AND (user_category IS NULL OR user_category = '')"
    )

    # Monthly Installments → Shopping (Apple device financing)
    op.execute(
        "UPDATE transactions SET ai_category = 'Shopping' "
        "WHERE description ILIKE '%monthly installments%' "
        "AND (user_category IS NULL OR user_category = '')"
    )

    # Zelle with "Sandra" / "cleaning" → Personal Care
    op.execute(
        "UPDATE transactions SET ai_category = 'Personal Care' "
        "WHERE description ILIKE '%zelle%' "
        "AND (description ILIKE '%sandra%' OR description ILIKE '%cleaning%' OR description ILIKE '%limpiez%') "
        "AND (user_category IS NULL OR user_category = '')"
    )

    # Zelle with "Brazas" → Restaurants
    op.execute(
        "UPDATE transactions SET ai_category = 'Restaurants' "
        "WHERE description ILIKE '%zelle%' "
        "AND description ILIKE '%brazas%' "
        "AND (user_category IS NULL OR user_category = '')"
    )


    # 4. Clear unhelpful Plaid categories when we have a better ai_category
    #    (Plaid "Other"/"Transfer Out" take priority over ai_category in coalesce chain)
    op.execute(
        "UPDATE transactions SET category = NULL "
        "WHERE category = 'Other' "
        "AND ai_category IS NOT NULL AND ai_category != 'Other' "
        "AND (user_category IS NULL OR user_category = '')"
    )
    op.execute(
        "UPDATE transactions SET category = NULL "
        "WHERE description ILIKE '%zelle%' "
        "AND category IN ('Transfer Out', 'TRANSFER_OUT') "
        "AND ai_category IS NOT NULL"
    )


def downgrade() -> None:
    pass  # Not reversible — display-time normalize_category() still works as fallback
