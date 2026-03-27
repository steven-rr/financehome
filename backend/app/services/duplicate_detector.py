"""Three-pass duplicate detection for CSV imports.

Modeled after Actual Budget's reconciliation approach:
  Pass 1 — Exact match: same csv ID, OR same financial_id extracted from description
  Pass 2 — Amount + date within 7 days + fuzzy payee (high confidence, user review)
  Pass 3 — Amount + date within 7 days only (low confidence, user review)
"""

import re
from collections import defaultdict
from datetime import date, timedelta
from difflib import SequenceMatcher

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.account import Account
from app.models.transaction import Transaction

# Prefixes commonly added by banks/POS systems that obscure the merchant name
_STRIP_PREFIXES = [
    "pos ", "pos-", "purchase ", "sq *", "sq*", "tst*", "tst ",
    "paypal *", "debit ", "ach ", "ach credit ", "ach debit ",
    "mobile purchase ", "recurring ",
]

FUZZY_MATCH_THRESHOLD = 0.6
DATE_WINDOW_DAYS = 7

# Patterns for extracting per-transaction identifiers from descriptions.
# ONLY patterns where the label guarantees a UNIQUE-PER-TRANSACTION value.
# Excluded: "ID:" in ACH descriptions — often a company/payroll ID reused
# across every transaction from the same sender (e.g., Lockheed payroll).
_FINANCIAL_ID_PATTERNS = [
    # Confirmation numbers: "Conf# qbav65xzo", "Conf #12345"
    re.compile(r'Conf\s*#\s*([A-Za-z0-9]+)'),
    # Reference numbers: "Ref# 12345", "Ref #ABC123"
    re.compile(r'Ref\s*#\s*([A-Za-z0-9]+)'),
    # Trace numbers: "Trace# 12345" (ACH trace, always per-transaction)
    re.compile(r'Trace\s*#\s*([A-Za-z0-9]+)'),
    # Check numbers: "Check# 4001", "Check #4001"
    re.compile(r'Check\s*#\s*([A-Za-z0-9]+)'),
    # Transaction IDs: "Trans# 12345", "Transaction# 12345"
    re.compile(r'Trans(?:action)?\s*#\s*([A-Za-z0-9]+)'),
]


def _extract_financial_id(description: str) -> str | None:
    """Extract a bank-embedded transaction ID from a description string.

    Returns the extracted ID or None if no recognizable pattern is found.
    """
    if not description:
        return None
    for pattern in _FINANCIAL_ID_PATTERNS:
        match = pattern.search(description)
        if match:
            return match.group(1)
    return None


def _normalize_payee(text: str) -> str:
    """Normalize a transaction description for fuzzy comparison."""
    text = text.lower().strip()
    for prefix in _STRIP_PREFIXES:
        if text.startswith(prefix):
            text = text[len(prefix):]
    # Collapse whitespace
    text = " ".join(text.split())
    return text


def _fuzzy_payee_score(csv_desc: str, existing_desc: str, existing_merchant: str | None) -> float:
    """Compare CSV description against existing transaction's description and merchant.

    Returns the higher of the two similarity ratios.
    """
    norm_csv = _normalize_payee(csv_desc)
    if not norm_csv:
        return 0.0

    scores = []
    if existing_desc:
        scores.append(SequenceMatcher(None, norm_csv, _normalize_payee(existing_desc)).ratio())
    if existing_merchant:
        scores.append(SequenceMatcher(None, norm_csv, _normalize_payee(existing_merchant)).ratio())

    return max(scores) if scores else 0.0


def _make_csv_id(row: dict) -> str:
    return f"csv-{row['date']}-{row['amount']}-{row['description'][:50]}"


async def detect_duplicates(
    db: AsyncSession,
    user_id,
    target_account_id,
    rows: list[dict],
) -> dict:
    """Run three-pass duplicate detection on parsed CSV rows.

    Returns:
        {
            "clean": [rows to auto-import],
            "skipped": [rows auto-skipped by Pass 1],
            "suspected_duplicates": [
                {
                    "csv_row": {...},
                    "existing_transaction": {...},
                    "confidence": "high" | "low",
                }
            ],
        }
    """
    if not rows:
        return {"clean": [], "skipped": [], "suspected_duplicates": []}

    # --- Fetch existing data ---

    # Same-account csv IDs for Pass 1a
    existing_ids_result = await db.execute(
        select(Transaction.plaid_transaction_id).where(
            Transaction.account_id == target_account_id,
        )
    )
    existing_ids = {r[0] for r in existing_ids_result.all()}

    # All user transactions in the date range for Pass 1b, 2, & 3
    csv_dates = {row["date"] for row in rows}
    min_date = min(csv_dates) - timedelta(days=DATE_WINDOW_DAYS)
    max_date = max(csv_dates) + timedelta(days=DATE_WINDOW_DAYS)

    existing_txns_result = await db.execute(
        select(
            Transaction.id,
            Transaction.date,
            Transaction.amount,
            Transaction.description,
            Transaction.merchant_name,
            Account.name.label("account_name"),
        )
        .join(Account, Transaction.account_id == Account.id)
        .where(
            Account.user_id == user_id,
            Transaction.date >= min_date,
            Transaction.date <= max_date,
        )
    )
    existing_txns = existing_txns_result.all()

    # Index by amount for efficient lookup (Pass 2 & 3)
    by_amount: defaultdict[str, list] = defaultdict(list)
    for txn in existing_txns:
        by_amount[str(txn.amount)].append(txn)

    # Build a set of financial IDs from existing transactions (Pass 1b)
    existing_financial_ids: set[str] = set()
    for txn in existing_txns:
        fid = _extract_financial_id(txn.description)
        if fid:
            existing_financial_ids.add(fid)

    # Track which existing transactions have already been matched
    matched_existing: set = set()

    # --- Pass 1: Exact match ---
    # 1a: Same csv-generated ID (same CSV uploaded twice)
    # 1b: Same financial_id extracted from description (CSV overlaps with Plaid)
    skipped = []
    remaining = []
    for row in rows:
        csv_id = _make_csv_id(row)
        if csv_id in existing_ids:
            skipped.append(row)
            existing_ids.add(csv_id)
            continue

        csv_fid = _extract_financial_id(row.get("description") or "")
        if csv_fid and csv_fid in existing_financial_ids:
            skipped.append(row)
            continue

        remaining.append(row)

    # --- Pass 2: Amount + date + fuzzy payee ---
    suspected = []
    still_remaining = []
    for row in remaining:
        amount_key = str(row["amount"])
        csv_date = row["date"]
        csv_desc = row.get("description") or ""
        found = False

        for txn in by_amount.get(amount_key, []):
            if id(txn) in matched_existing:
                continue
            delta = abs((csv_date - txn.date).days)
            if delta > DATE_WINDOW_DAYS:
                continue

            score = _fuzzy_payee_score(csv_desc, txn.description, txn.merchant_name)
            if score >= FUZZY_MATCH_THRESHOLD:
                matched_existing.add(id(txn))
                suspected.append({
                    "csv_row": row,
                    "existing_transaction": {
                        "id": str(txn.id),
                        "date": str(txn.date),
                        "amount": float(txn.amount),
                        "description": txn.description,
                        "merchant_name": txn.merchant_name,
                        "account_name": txn.account_name,
                    },
                    "confidence": "high",
                })
                found = True
                break

        if not found:
            still_remaining.append(row)

    # --- Pass 3: Amount + date only ---
    clean = []
    for row in still_remaining:
        amount_key = str(row["amount"])
        csv_date = row["date"]
        found = False

        for txn in by_amount.get(amount_key, []):
            if id(txn) in matched_existing:
                continue
            delta = abs((csv_date - txn.date).days)
            if delta > DATE_WINDOW_DAYS:
                continue

            matched_existing.add(id(txn))
            suspected.append({
                "csv_row": row,
                "existing_transaction": {
                    "id": str(txn.id),
                    "date": str(txn.date),
                    "amount": float(txn.amount),
                    "description": txn.description,
                    "merchant_name": txn.merchant_name,
                    "account_name": txn.account_name,
                },
                "confidence": "low",
            })
            found = True
            break

        if not found:
            clean.append(row)

    return {
        "clean": clean,
        "skipped": skipped,
        "suspected_duplicates": suspected,
    }
