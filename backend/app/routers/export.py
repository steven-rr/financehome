import csv
import io
from datetime import date, timedelta

from fastapi import APIRouter, Depends, Query
from fastapi.responses import StreamingResponse
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.models.account import Account
from app.models.transaction import Transaction
from app.models.user import User
from app.routers.auth import get_current_user

router = APIRouter()


@router.get("/transactions")
async def export_transactions_csv(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    start_date: date | None = Query(None),
    end_date: date | None = Query(None),
):
    if not end_date:
        end_date = date.today()
    if not start_date:
        start_date = end_date - timedelta(days=90)

    # Query transactions joined with account names
    result = await db.execute(
        select(Transaction, Account.name.label("account_name"))
        .join(Account, Transaction.account_id == Account.id)
        .where(
            Account.user_id == current_user.id,
            Transaction.date >= start_date,
            Transaction.date <= end_date,
        )
        .order_by(Transaction.date.desc())
    )
    rows = result.all()

    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(["Date", "Merchant", "Description", "Category", "Amount", "Type", "Account", "Status"])

    for txn, account_name in rows:
        writer.writerow([
            txn.date,
            txn.merchant_name or "",
            txn.description,
            txn.category or "Uncategorized",
            round(abs(txn.amount), 2),
            "Expense" if txn.amount > 0 else "Income",
            account_name,
            "Pending" if txn.is_pending else "Posted",
        ])

    output.seek(0)
    filename = f"transactions_{start_date}_{end_date}.csv"

    return StreamingResponse(
        iter([output.getvalue()]),
        media_type="text/csv",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )
