import random
import uuid
from datetime import date, timedelta

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.account import Account
from app.models.plaid_link import PlaidLink
from app.models.transaction import Transaction
from app.models.user import User
from app.utils.security import hash_password

DEMO_EMAIL = "demo@financehome.app"
DEMO_PASSWORD_HASH = hash_password("demo-not-a-real-password")

# Merchant table: (merchant, category, subcategory, min_amt, max_amt, per_month, account_key)
EXPENSE_MERCHANTS = [
    ("Amazon", "Shopping", "Online", 15.0, 120.0, 4, "checking"),
    ("Starbucks", "Food & Drink", "Coffee", 4.50, 7.50, 8, "credit"),
    ("Uber", "Transportation", "Rideshare", 8.0, 35.0, 3, "credit"),
    ("Whole Foods", "Food & Drink", "Groceries", 45.0, 130.0, 4, "checking"),
    ("Netflix", "Entertainment", "Streaming", 15.49, 15.49, 1, "credit"),
    ("Spotify", "Entertainment", "Streaming", 10.99, 10.99, 1, "credit"),
    ("Shell Gas", "Transportation", "Gas", 35.0, 65.0, 3, "checking"),
    ("Target", "Shopping", "Department Store", 20.0, 80.0, 2, "credit"),
    ("Chipotle", "Food & Drink", "Restaurants", 10.0, 18.0, 3, "credit"),
    ("Con Edison", "Utilities", "Electric", 85.0, 145.0, 1, "checking"),
    ("AT&T", "Utilities", "Phone", 95.0, 95.0, 1, "checking"),
    ("Planet Fitness", "Health", "Gym", 24.99, 24.99, 1, "checking"),
    ("CVS Pharmacy", "Health", "Pharmacy", 8.0, 45.0, 2, "credit"),
    ("Trader Joe's", "Food & Drink", "Groceries", 30.0, 90.0, 3, "checking"),
    ("Home Depot", "Home", "Home Improvement", 25.0, 200.0, 1, "credit"),
    ("DoorDash", "Food & Drink", "Delivery", 18.0, 45.0, 3, "credit"),
    ("Costco", "Shopping", "Wholesale", 80.0, 250.0, 1, "checking"),
    ("Apple", "Shopping", "Electronics", 0.99, 14.99, 1, "credit"),
]

INCOME_MERCHANTS = [
    ("Acme Corp - Payroll", "Income", "Salary", 3200.0, 3200.0, 2, "checking"),
    ("Interest Payment", "Income", "Interest", 2.50, 8.50, 1, "savings"),
]

ACCOUNTS_CONFIG = {
    "checking": {
        "name": "Everyday Checking",
        "official_name": "Chase Total Checking",
        "type": "depository",
        "subtype": "checking",
        "balance_current": 4285.43,
        "balance_available": 4185.43,
        "plaid_account_id": "demo-acct-checking",
    },
    "savings": {
        "name": "High-Yield Savings",
        "official_name": "Chase Savings",
        "type": "depository",
        "subtype": "savings",
        "balance_current": 12750.00,
        "balance_available": 12750.00,
        "plaid_account_id": "demo-acct-savings",
    },
    "credit": {
        "name": "Sapphire Card",
        "official_name": "Chase Sapphire Preferred",
        "type": "credit",
        "subtype": "credit card",
        "balance_current": 1847.32,
        "balance_available": 8152.68,
        "plaid_account_id": "demo-acct-credit",
    },
}


def _generate_transactions(
    account_map: dict[str, uuid.UUID],
    start_date: date,
    end_date: date,
) -> list[dict]:
    rng = random.Random(42)
    transactions = []
    txn_counter = 0
    total_days = (end_date - start_date).days

    for merchant, category, subcategory, min_amt, max_amt, per_month, acct_key in EXPENSE_MERCHANTS:
        count = max(1, int(per_month * total_days / 30))
        for _ in range(count):
            day_offset = rng.randint(0, total_days)
            txn_date = start_date + timedelta(days=day_offset)
            amount = round(rng.uniform(min_amt, max_amt), 2)
            txn_counter += 1
            transactions.append({
                "account_id": account_map[acct_key],
                "plaid_transaction_id": f"demo-txn-{txn_counter:04d}",
                "date": txn_date,
                "amount": amount,  # positive = expense
                "merchant_name": merchant,
                "description": f"{merchant} purchase",
                "category": category,
                "subcategory": subcategory,
                "is_pending": txn_date >= end_date - timedelta(days=2),
            })

    for merchant, category, subcategory, min_amt, max_amt, per_month, acct_key in INCOME_MERCHANTS:
        if "Payroll" in merchant:
            # Fixed schedule: 1st and 15th of each month for realistic paychecks
            d = start_date.replace(day=1)
            while d <= end_date:
                for pay_day in (1, 15):
                    txn_date = d.replace(day=pay_day)
                    if start_date <= txn_date <= end_date:
                        amount = -round(rng.uniform(min_amt, max_amt), 2)
                        txn_counter += 1
                        transactions.append({
                            "account_id": account_map[acct_key],
                            "plaid_transaction_id": f"demo-txn-{txn_counter:04d}",
                            "date": txn_date,
                            "amount": amount,
                            "merchant_name": merchant,
                            "description": f"{merchant} deposit",
                            "category": category,
                            "subcategory": subcategory,
                            "is_pending": False,
                        })
                # Advance to next month
                if d.month == 12:
                    d = d.replace(year=d.year + 1, month=1)
                else:
                    d = d.replace(month=d.month + 1)
        else:
            count = max(1, int(per_month * total_days / 30))
            for _ in range(count):
                day_offset = rng.randint(0, total_days)
                txn_date = start_date + timedelta(days=day_offset)
                amount = -round(rng.uniform(min_amt, max_amt), 2)  # negative = income
                txn_counter += 1
                transactions.append({
                    "account_id": account_map[acct_key],
                    "plaid_transaction_id": f"demo-txn-{txn_counter:04d}",
                    "date": txn_date,
                    "amount": amount,
                    "merchant_name": merchant,
                    "description": f"{merchant} deposit",
                    "category": category,
                    "subcategory": subcategory,
                    "is_pending": False,
                })

    return transactions


async def seed_demo_data(db: AsyncSession) -> User:
    """Delete existing demo data and create fresh demo user with seed data."""

    # Find and delete existing demo user (cascade removes all related data)
    result = await db.execute(select(User).where(User.email == DEMO_EMAIL))
    existing = result.scalar_one_or_none()
    if existing:
        await db.delete(existing)
        await db.flush()

    # Create demo user
    user = User(email=DEMO_EMAIL, password_hash=DEMO_PASSWORD_HASH)
    db.add(user)
    await db.flush()

    # Create dummy PlaidLink (required FK for accounts)
    plaid_link = PlaidLink(
        user_id=user.id,
        access_token="demo-access-token",
        item_id="demo-item-001",
        institution_name="Chase",
        status="active",
    )
    db.add(plaid_link)
    await db.flush()

    # Create accounts
    account_map: dict[str, uuid.UUID] = {}
    for key, config in ACCOUNTS_CONFIG.items():
        account = Account(
            user_id=user.id,
            plaid_link_id=plaid_link.id,
            **config,
            currency="USD",
        )
        db.add(account)
        await db.flush()
        account_map[key] = account.id

    # Generate and insert transactions
    end_date = date.today()
    start_date = end_date - timedelta(days=90)
    txn_dicts = _generate_transactions(account_map, start_date, end_date)

    for txn_data in txn_dicts:
        db.add(Transaction(**txn_data))

    await db.commit()
    return user
