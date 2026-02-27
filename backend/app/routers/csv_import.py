import csv
import io
import uuid
from datetime import datetime

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.models.account import Account
from app.models.plaid_link import PlaidLink
from app.models.transaction import Transaction
from app.models.user import User
from app.routers.auth import get_current_user

router = APIRouter()

# Apple Card CSV columns: Transaction Date, Clearing Date, Description, Merchant, Category, Type, Amount
APPLE_CARD_HEADERS = {"transaction date", "clearing date", "description", "merchant", "category", "type", "amount"}


def detect_and_parse_csv(content: str) -> list[dict]:
    """Parse CSV and normalize rows to a common format."""
    reader = csv.DictReader(io.StringIO(content))
    if not reader.fieldnames:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="CSV file is empty or has no headers")

    headers_lower = {h.strip().lower() for h in reader.fieldnames}

    # Detect Apple Card format (Amount or Amount (USD))
    if headers_lower >= {"transaction date", "description"} and (
        "amount" in headers_lower or "amount (usd)" in headers_lower
    ):
        return _parse_apple_card(reader)

    # Detect Capital One (Spanish headers)
    if headers_lower >= {"fecha de transacción", "descripción", "débito"}:
        return _parse_capital_one(reader)

    # Generic fallback: expect date, description, amount at minimum
    if headers_lower >= {"date", "description", "amount"}:
        return _parse_generic(reader)

    raise HTTPException(
        status_code=status.HTTP_400_BAD_REQUEST,
        detail=f"Unrecognized CSV format. Headers found: {reader.fieldnames}. "
               "Expected Apple Card, Capital One, or generic format (Date, Description, Amount).",
    )


def _parse_apple_card(reader: csv.DictReader) -> list[dict]:
    rows = []
    for raw in reader:
        row = {k.strip().lower(): v.strip() for k, v in raw.items() if k}
        try:
            txn_date = datetime.strptime(row["transaction date"], "%m/%d/%Y").date()
        except ValueError:
            txn_date = datetime.strptime(row["transaction date"], "%Y-%m-%d").date()

        amount_str = (row.get("amount (usd)") or row.get("amount") or "0").replace(",", "")
        amount = float(amount_str)

        # Apple Card: positive = purchase (expense), negative = payment/refund (income)
        rows.append({
            "date": txn_date,
            "amount": amount,
            "merchant_name": row.get("merchant", "").strip() or None,
            "description": row.get("description", "").strip(),
            "category": row.get("category", "").strip() or None,
        })
    return rows


def _parse_capital_one(reader: csv.DictReader) -> list[dict]:
    rows = []
    for raw in reader:
        row = {k.strip().lower(): v.strip() for k, v in raw.items() if k}
        date_str = row.get("fecha de transacción", "")
        try:
            txn_date = datetime.strptime(date_str, "%Y-%m-%d").date()
        except ValueError:
            txn_date = datetime.strptime(date_str, "%m/%d/%Y").date()

        debit = row.get("débito", "").replace(",", "").strip()
        credit = row.get("crédito", "").replace(",", "").strip()

        if debit:
            amount = float(debit)  # positive = expense
        elif credit:
            amount = -float(credit)  # negative = payment/income
        else:
            continue

        description = row.get("descripción", "").strip()
        category = row.get("categoría", "").strip() or None

        rows.append({
            "date": txn_date,
            "amount": amount,
            "merchant_name": None,
            "description": description,
            "category": category,
        })
    return rows


def _parse_generic(reader: csv.DictReader) -> list[dict]:
    rows = []
    for raw in reader:
        row = {k.strip().lower(): v.strip() for k, v in raw.items() if k}
        date_str = row["date"]
        for fmt in ("%m/%d/%Y", "%Y-%m-%d", "%m/%d/%y", "%d/%m/%Y"):
            try:
                txn_date = datetime.strptime(date_str, fmt).date()
                break
            except ValueError:
                continue
        else:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Could not parse date: {date_str}",
            )

        amount_str = row.get("amount", "0").replace(",", "").replace("$", "")
        amount = float(amount_str)

        rows.append({
            "date": txn_date,
            "amount": amount,
            "merchant_name": row.get("merchant", "").strip() or row.get("merchant_name", "").strip() or None,
            "description": row.get("description", "").strip(),
            "category": row.get("category", "").strip() or None,
        })
    return rows


async def _get_or_create_manual_account(
    db: AsyncSession,
    user: User,
    account_name: str,
) -> Account:
    """Find or create a manual (non-Plaid) account for CSV imports."""
    result = await db.execute(
        select(Account).where(
            Account.user_id == user.id,
            Account.name == account_name,
            Account.plaid_account_id.like("manual-%"),
        )
    )
    account = result.scalar_one_or_none()
    if account:
        return account

    # Create a dummy PlaidLink for the FK constraint
    plaid_link = PlaidLink(
        user_id=user.id,
        access_token="manual-import",
        item_id=f"manual-{uuid.uuid4().hex[:12]}",
        institution_name=account_name,
        status="active",
    )
    db.add(plaid_link)
    await db.flush()

    account = Account(
        user_id=user.id,
        plaid_link_id=plaid_link.id,
        plaid_account_id=f"manual-{uuid.uuid4().hex[:12]}",
        name=account_name,
        type="credit",
        subtype="credit card",
        currency="USD",
    )
    db.add(account)
    await db.flush()
    return account


@router.post("/transactions")
async def import_transactions_csv(
    file: UploadFile = File(...),
    account_name: str = Form(default="Apple Card"),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    if not file.filename or not file.filename.endswith(".csv"):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="File must be a .csv")

    content = (await file.read()).decode("utf-8-sig")  # utf-8-sig handles BOM
    rows = detect_and_parse_csv(content)

    if not rows:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="No transactions found in CSV")

    account = await _get_or_create_manual_account(db, current_user, account_name)

    # Get existing transaction IDs to avoid duplicates
    existing = await db.execute(
        select(Transaction.plaid_transaction_id).where(
            Transaction.account_id == account.id,
        )
    )
    existing_ids = {r[0] for r in existing.all()}

    imported = 0
    skipped = 0
    for row in rows:
        # Create a deterministic ID from date + amount + description to detect duplicates
        txn_id = f"csv-{row['date']}-{row['amount']}-{row['description'][:50]}"
        if txn_id in existing_ids:
            skipped += 1
            continue

        db.add(Transaction(
            account_id=account.id,
            plaid_transaction_id=txn_id,
            date=row["date"],
            amount=row["amount"],
            merchant_name=row["merchant_name"],
            description=row["description"],
            category=row["category"],
            is_pending=False,
        ))
        existing_ids.add(txn_id)
        imported += 1

    await db.commit()
    return {"imported": imported, "skipped": skipped, "total_in_file": len(rows)}
