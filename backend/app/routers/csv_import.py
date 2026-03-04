import csv
import io
import json
import uuid
from datetime import datetime

from fastapi import APIRouter, Depends, File, Form, HTTPException, Request, UploadFile, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.models.account import Account
from app.models.plaid_link import PlaidLink
from app.models.transaction import Transaction
from app.models.user import User
from app.rate_limit import limiter
from app.routers.auth import get_current_user
from app.services.analytics_service import normalize_category
from app.services.gemini_categorizer import TransactionCategorizer

router = APIRouter()


def _is_csv_filename(filename: str) -> bool:
    return filename.lower().endswith(".csv")


def _decode_csv(raw: bytes) -> str:
    """Decode CSV bytes, trying UTF-8 first then falling back to Latin-1."""
    try:
        return raw.decode("utf-8-sig")
    except UnicodeDecodeError:
        return raw.decode("latin-1")


def detect_and_parse_csv(content: str) -> list[dict]:
    """Parse CSV and normalize rows to a common format.

    All parsers normalize amounts to Plaid convention:
      positive = expense (money out), negative = income (money in)
    """
    # Check if this is a bank statement with summary rows at the top
    lines = content.strip().splitlines()
    if lines and _looks_like_bank_statement(lines):
        return _parse_bank_statement(content)

    reader = csv.DictReader(io.StringIO(content))
    if not reader.fieldnames:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="CSV file is empty or has no headers")

    headers_lower = {h.strip().lower() for h in reader.fieldnames}

    # Chase credit card: has "post date" and "memo" columns
    if headers_lower >= {"transaction date", "post date", "description", "amount"}:
        return _parse_chase(reader)

    # Apple Card: has "clearing date" or "merchant" columns (no "post date")
    if headers_lower >= {"transaction date", "description"} and (
        "amount" in headers_lower or "amount (usd)" in headers_lower
    ):
        return _parse_apple_card(reader)

    # Citi: has Status, Debit, Credit columns (no single Amount column)
    if headers_lower >= {"status", "date", "description", "debit", "credit"}:
        return _parse_citi(reader)

    # Capital One (English): Transaction Date, Posted Date, Card No., Description, Category, Debit, Credit
    if headers_lower >= {"transaction date", "posted date", "card no.", "description", "debit", "credit"}:
        return _parse_capital_one(reader)

    # Capital One (Spanish headers)
    if headers_lower >= {"fecha de transacción", "descripción", "débito"}:
        return _parse_capital_one_spanish(reader)

    # Generic fallback: expect date, description, amount at minimum
    if headers_lower >= {"date", "description", "amount"}:
        return _parse_generic(reader)

    raise HTTPException(
        status_code=status.HTTP_400_BAD_REQUEST,
        detail=f"Unrecognized CSV format. Headers found: {reader.fieldnames}. "
               "Supported: Chase, Apple Card, Citi, Capital One, bank statement, or generic (Date, Description, Amount).",
    )


def _looks_like_bank_statement(lines: list[str]) -> bool:
    """Detect bank statement format with summary header then data rows."""
    for line in lines[:10]:
        stripped = line.strip().lower()
        if stripped.startswith("date,description,amount"):
            return True
    return False


def _parse_bank_statement(content: str) -> list[dict]:
    """Parse bank statement CSV with summary rows at top, data rows below."""
    # Find the "Date,Description,Amount" header in the raw content
    # Use string search instead of splitlines to preserve CSV quoting
    lower_content = content.lower()
    marker = "date,description,amount"
    pos = lower_content.find(marker)

    if pos == -1:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Could not find transaction data in bank statement")

    # Find the start of the line containing the marker
    line_start = content.rfind("\n", 0, pos)
    data_content = content[line_start + 1:] if line_start != -1 else content[pos:]

    reader = csv.DictReader(io.StringIO(data_content))

    rows = []
    for raw in reader:
        row = {k.strip().lower(): (v.strip() if v else "") for k, v in raw.items() if k}
        date_str = row.get("date", "").strip()
        description = row.get("description", "").strip()
        amount_str = row.get("amount", "").replace(",", "").replace('"', "").strip()

        if not date_str or not amount_str or not description:
            continue

        # Skip "Beginning balance" and "Ending balance" rows
        if "beginning balance" in description.lower() or "ending balance" in description.lower():
            continue

        for fmt in ("%m/%d/%Y", "%Y-%m-%d", "%m/%d/%y"):
            try:
                txn_date = datetime.strptime(date_str, fmt).date()
                break
            except ValueError:
                continue
        else:
            continue  # Skip rows with unparseable dates

        try:
            amount = float(amount_str)
        except ValueError:
            continue  # Skip rows with unparseable amounts

        # Bank statement: negative = money out (debit), positive = money in (credit)
        # Flip to Plaid convention: positive = expense, negative = income
        amount = -amount

        rows.append({
            "date": txn_date,
            "amount": round(amount, 2),
            "merchant_name": None,
            "description": description,
            "category": None,
        })
    return rows


def _parse_chase(reader: csv.DictReader) -> list[dict]:
    """Parse Chase credit card CSV.

    Chase: negative = purchase (expense), positive = payment/credit (income).
    Flip sign to match Plaid convention.
    """
    rows = []
    for raw in reader:
        row = {k.strip().lower(): v.strip() for k, v in raw.items() if k}
        date_str = row.get("transaction date", "")
        try:
            txn_date = datetime.strptime(date_str, "%m/%d/%Y").date()
        except ValueError:
            txn_date = datetime.strptime(date_str, "%Y-%m-%d").date()

        amount_str = row.get("amount", "0").replace(",", "")
        amount = float(amount_str)
        # Chase: -24.28 = expense, +352.76 = payment
        # Flip: +24.28 = expense, -352.76 = income
        amount = -amount

        rows.append({
            "date": txn_date,
            "amount": round(amount, 2),
            "merchant_name": None,
            "description": row.get("description", "").strip(),
            "category": row.get("category", "").strip() or None,
        })
    return rows


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
        # Already matches Plaid convention
        rows.append({
            "date": txn_date,
            "amount": amount,
            "merchant_name": row.get("merchant", "").strip() or None,
            "description": row.get("description", "").strip(),
            "category": row.get("category", "").strip() or None,
        })
    return rows


def _parse_citi(reader: csv.DictReader) -> list[dict]:
    """Parse Citi credit card CSV.

    Citi uses separate Debit/Credit columns.
    Debit = expense (positive), Credit = payment/refund (negative in CSV).
    Both already align with Plaid convention.
    """
    rows = []
    for raw in reader:
        row = {k.strip().lower(): (v.strip() if v else "") for k, v in raw.items() if k}
        date_str = row.get("date", "")
        if not date_str:
            continue

        try:
            txn_date = datetime.strptime(date_str, "%m/%d/%Y").date()
        except ValueError:
            try:
                txn_date = datetime.strptime(date_str, "%Y-%m-%d").date()
            except ValueError:
                continue

        debit_str = row.get("debit", "").replace(",", "").strip()
        credit_str = row.get("credit", "").replace(",", "").strip()

        if debit_str:
            amount = float(debit_str)   # positive = expense
        elif credit_str:
            amount = float(credit_str)  # negative = payment/income
        else:
            continue

        description = row.get("description", "").strip()
        if not description:
            continue

        rows.append({
            "date": txn_date,
            "amount": round(amount, 2),
            "merchant_name": None,
            "description": description,
            "category": None,
        })
    return rows


def _parse_capital_one(reader: csv.DictReader) -> list[dict]:
    """Parse Capital One credit card CSV (English).

    Capital One uses separate Debit/Credit columns.
    Debit = expense (positive), Credit = payment (negative).
    """
    rows = []
    for raw in reader:
        row = {k.strip().lower(): v.strip() for k, v in raw.items() if k}
        date_str = row.get("transaction date", "")
        if not date_str:
            continue

        try:
            txn_date = datetime.strptime(date_str, "%Y-%m-%d").date()
        except ValueError:
            try:
                txn_date = datetime.strptime(date_str, "%m/%d/%Y").date()
            except ValueError:
                continue

        debit = row.get("debit", "").replace(",", "").strip()
        credit = row.get("credit", "").replace(",", "").strip()

        if debit:
            amount = float(debit)  # positive = expense
        elif credit:
            amount = -float(credit)  # negative = payment/income
        else:
            continue

        description = row.get("description", "").strip()
        category = row.get("category", "").strip() or None

        rows.append({
            "date": txn_date,
            "amount": round(amount, 2),
            "merchant_name": None,
            "description": description,
            "category": category,
        })
    return rows


def _parse_capital_one_spanish(reader: csv.DictReader) -> list[dict]:
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
@limiter.limit("10/minute")
async def import_transactions_csv(
    request: Request,
    file: UploadFile = File(...),
    account_name: str = Form(default="Apple Card"),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    if not file.filename or not _is_csv_filename(file.filename):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="File must be a .csv")

    content = _decode_csv(await file.read())  # utf-8-sig handles BOM
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
            category=normalize_category(row["category"]) if row.get("category") else None,
            is_pending=False,
        ))
        existing_ids.add(txn_id)
        imported += 1

    await db.commit()

    # Auto-categorize newly imported transactions
    if imported > 0:
        categorizer = TransactionCategorizer()
        await categorizer.categorize_uncategorized(current_user.id, db)

    return {"imported": imported, "skipped": skipped, "total_in_file": len(rows)}


@router.post("/transactions/bulk")
@limiter.limit("5/minute")
async def import_transactions_bulk(
    request: Request,
    files: list[UploadFile] = File(...),
    account_mappings: str = Form(default="{}"),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Import multiple CSV files at once.

    account_mappings is a JSON string mapping filename to target account:
      { "file.csv": { "account_id": "uuid" } }       — import into existing account
      { "file.csv": { "new_name": "My Account" } }    — create new manual account
    Files not in the mapping derive account name from filename (backwards compatible).
    """
    if not files:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="No files provided")

    try:
        mappings = json.loads(account_mappings)
    except json.JSONDecodeError:
        mappings = {}

    total_imported = 0
    total_skipped = 0
    total_in_files = 0
    file_results = []

    for file in files:
        if not file.filename or not _is_csv_filename(file.filename):
            file_results.append({"file": file.filename or "unknown", "error": "Not a .csv file"})
            continue

        try:
            content = _decode_csv(await file.read())
            rows = detect_and_parse_csv(content)
        except HTTPException as e:
            file_results.append({"file": file.filename, "error": e.detail})
            continue

        if not rows:
            file_results.append({"file": file.filename, "error": "No transactions found"})
            continue

        # Resolve target account from mapping or filename
        mapping = mappings.get(file.filename, {})
        if mapping.get("account_id"):
            # Use existing account — verify ownership
            result = await db.execute(
                select(Account).where(
                    Account.id == mapping["account_id"],
                    Account.user_id == current_user.id,
                )
            )
            account = result.scalar_one_or_none()
            if not account:
                file_results.append({"file": file.filename, "error": "Account not found"})
                continue
            account_name = account.name
        else:
            account_name = mapping.get("new_name") or file.filename.rsplit(".", 1)[0]
            account = await _get_or_create_manual_account(db, current_user, account_name)

        existing = await db.execute(
            select(Transaction.plaid_transaction_id).where(
                Transaction.account_id == account.id,
            )
        )
        existing_ids = {r[0] for r in existing.all()}

        imported = 0
        skipped = 0
        for row in rows:
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
                category=normalize_category(row["category"]) if row.get("category") else None,
                is_pending=False,
            ))
            existing_ids.add(txn_id)
            imported += 1

        total_imported += imported
        total_skipped += skipped
        total_in_files += len(rows)
        file_results.append({
            "file": file.filename,
            "account": account_name,
            "imported": imported,
            "skipped": skipped,
            "total_in_file": len(rows),
        })

    await db.commit()

    # Auto-categorize newly imported transactions
    if total_imported > 0:
        categorizer = TransactionCategorizer()
        await categorizer.categorize_uncategorized(current_user.id, db)

    return {
        "imported": total_imported,
        "skipped": total_skipped,
        "total_in_files": total_in_files,
        "files": file_results,
    }
