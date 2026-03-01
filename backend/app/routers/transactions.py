import uuid
from datetime import date, timedelta

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy import Select, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.models.account import Account
from app.models.transaction import Transaction
from app.models.user import User
from app.routers.auth import get_current_user
from app.services.analytics_service import effective_category_expr, normalize_category

router = APIRouter()


class TransactionResponse(BaseModel):
    id: uuid.UUID
    account_id: uuid.UUID
    date: date
    amount: float
    merchant_name: str | None
    description: str
    category: str | None
    subcategory: str | None
    ai_category: str | None
    user_category: str | None
    notes: str | None
    is_pending: bool

    model_config = {"from_attributes": True}


class PaginatedTransactions(BaseModel):
    items: list[TransactionResponse]
    total: int
    page: int
    per_page: int
    pages: int


class CategorySummary(BaseModel):
    category: str
    total: float
    count: int


class IncomeExpenseSummary(BaseModel):
    income: float
    expenses: float
    net: float


class IncomeTransaction(BaseModel):
    date: date
    description: str
    merchant_name: str | None
    amount: float


class ExpenseTransaction(BaseModel):
    id: uuid.UUID
    date: date
    description: str
    merchant_name: str | None
    amount: float
    category: str
    subcategory: str | None = None
    ai_category: str | None = None
    user_category: str | None = None
    notes: str | None = None
    is_pending: bool = False


class TransactionUpdate(BaseModel):
    user_category: str | None = None
    notes: str | None = None


class MonthlyTrend(BaseModel):
    month: str  # "2025-01"
    income: float
    expenses: float
    net: float


def _base_query(user_id: uuid.UUID) -> Select:
    return (
        select(Transaction)
        .join(Account, Transaction.account_id == Account.id)
        .where(Account.user_id == user_id)
    )


@router.get("", response_model=PaginatedTransactions)
async def list_transactions(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    start_date: date | None = Query(None),
    end_date: date | None = Query(None),
    account_id: uuid.UUID | None = Query(None),
    category: str | None = Query(None),
    search: str | None = Query(None),
    page: int = Query(1, ge=1),
    per_page: int = Query(50, ge=1, le=200),
):
    query = _base_query(current_user.id)

    if start_date:
        query = query.where(Transaction.date >= start_date)
    if end_date:
        query = query.where(Transaction.date <= end_date)
    if account_id:
        query = query.where(Transaction.account_id == account_id)
    if category:
        query = query.where(effective_category_expr() == category)
    if search:
        search_pattern = f"%{search}%"
        query = query.where(
            Transaction.description.ilike(search_pattern)
            | Transaction.merchant_name.ilike(search_pattern)
        )

    # Count total
    count_query = select(func.count()).select_from(query.subquery())
    total_result = await db.execute(count_query)
    total = total_result.scalar() or 0

    # Paginate
    query = query.order_by(Transaction.date.desc()).offset((page - 1) * per_page).limit(per_page)
    result = await db.execute(query)
    transactions = result.scalars().all()

    items = []
    for t in transactions:
        item = TransactionResponse.model_validate(t)
        if item.category:
            item.category = normalize_category(item.category)
        if item.ai_category:
            item.ai_category = normalize_category(item.ai_category)
        if item.user_category:
            item.user_category = normalize_category(item.user_category)
        items.append(item)

    return PaginatedTransactions(
        items=items,
        total=total,
        page=page,
        per_page=per_page,
        pages=(total + per_page - 1) // per_page if total > 0 else 0,
    )


@router.patch("/{transaction_id}", response_model=TransactionResponse)
async def update_transaction(
    transaction_id: uuid.UUID,
    body: TransactionUpdate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(Transaction)
        .join(Account, Transaction.account_id == Account.id)
        .where(Account.user_id == current_user.id)
        .where(Transaction.id == transaction_id)
    )
    txn = result.scalar_one_or_none()
    if not txn:
        raise HTTPException(status_code=404, detail="Transaction not found")

    update_data = body.model_dump(exclude_unset=True)
    for field, value in update_data.items():
        setattr(txn, field, value)

    await db.commit()
    await db.refresh(txn)

    item = TransactionResponse.model_validate(txn)
    if item.category:
        item.category = normalize_category(item.category)
    if item.ai_category:
        item.ai_category = normalize_category(item.ai_category)
    if item.user_category:
        item.user_category = normalize_category(item.user_category)
    return item


@router.get("/income-expenses", response_model=IncomeExpenseSummary)
async def get_income_expenses(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    start_date: date | None = Query(None),
    end_date: date | None = Query(None),
):
    from app.services.analytics_service import TRANSFER_CATEGORIES, _is_cc_payment

    query = (
        select(Transaction.amount)
        .join(Account, Transaction.account_id == Account.id)
        .where(Account.user_id == current_user.id)
        .where(or_(
            effective_category_expr().is_(None),
            effective_category_expr().notin_(TRANSFER_CATEGORIES),
        ))
        .where(~_is_cc_payment())
    )

    if start_date:
        query = query.where(Transaction.date >= start_date)
    if end_date:
        query = query.where(Transaction.date <= end_date)

    result = await db.execute(query)
    amounts = [row[0] for row in result.all()]
    expenses = sum(a for a in amounts if a > 0)
    income = abs(sum(a for a in amounts if a < 0))

    return IncomeExpenseSummary(
        income=round(income, 2),
        expenses=round(expenses, 2),
        net=round(income - expenses, 2),
    )


@router.get("/income", response_model=list[IncomeTransaction])
async def get_income_transactions(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    start_date: date | None = Query(None),
    end_date: date | None = Query(None),
):
    from app.services.analytics_service import TRANSFER_CATEGORIES, _is_cc_payment

    query = (
        select(Transaction.date, Transaction.description, Transaction.merchant_name, Transaction.amount)
        .join(Account, Transaction.account_id == Account.id)
        .where(Account.user_id == current_user.id)
        .where(Transaction.amount < 0)
        .where(or_(
            effective_category_expr().is_(None),
            effective_category_expr().notin_(TRANSFER_CATEGORIES),
        ))
        .where(~_is_cc_payment())
        .order_by(Transaction.date.desc())
    )

    if start_date:
        query = query.where(Transaction.date >= start_date)
    if end_date:
        query = query.where(Transaction.date <= end_date)

    result = await db.execute(query)
    return [
        IncomeTransaction(
            date=row.date,
            description=row.description,
            merchant_name=row.merchant_name,
            amount=round(abs(row.amount), 2),
        )
        for row in result.all()
    ]


@router.get("/expenses", response_model=list[ExpenseTransaction])
async def get_expense_transactions(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    start_date: date | None = Query(None),
    end_date: date | None = Query(None),
):
    from app.services.analytics_service import TRANSFER_CATEGORIES, _is_cc_payment

    query = (
        select(
            Transaction.id, Transaction.date, Transaction.description,
            Transaction.merchant_name, Transaction.amount,
            Transaction.subcategory, Transaction.ai_category,
            Transaction.user_category, Transaction.notes, Transaction.is_pending,
            effective_category_expr().label("effective_category"),
        )
        .join(Account, Transaction.account_id == Account.id)
        .where(Account.user_id == current_user.id)
        .where(Transaction.amount > 0)
        .where(or_(
            effective_category_expr().is_(None),
            effective_category_expr().notin_(TRANSFER_CATEGORIES),
        ))
        .where(~_is_cc_payment())
        .order_by(Transaction.date.desc())
    )

    if start_date:
        query = query.where(Transaction.date >= start_date)
    if end_date:
        query = query.where(Transaction.date <= end_date)

    result = await db.execute(query)
    return [
        ExpenseTransaction(
            id=row.id,
            date=row.date,
            description=row.description,
            merchant_name=row.merchant_name,
            amount=round(row.amount, 2),
            category=normalize_category(row.effective_category or "Uncategorized"),
            subcategory=row.subcategory,
            ai_category=row.ai_category,
            user_category=row.user_category,
            notes=row.notes,
            is_pending=row.is_pending,
        )
        for row in result.all()
    ]


@router.get("/categories", response_model=list[CategorySummary])
async def get_category_summary(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    start_date: date | None = Query(None),
    end_date: date | None = Query(None),
):
    from app.services.analytics_service import TRANSFER_CATEGORIES, _is_cc_payment

    effective_category = effective_category_expr()
    query = (
        select(
            effective_category.label("category"),
            func.sum(Transaction.amount).label("total"),
            func.count().label("count"),
        )
        .join(Account, Transaction.account_id == Account.id)
        .where(Account.user_id == current_user.id)
        .where(Transaction.amount > 0)  # Expenses only (Plaid: positive = money out)
        .where(or_(
            effective_category.is_(None),
            effective_category.notin_(TRANSFER_CATEGORIES),
        ))
        .where(~_is_cc_payment())
        .group_by(effective_category)
        .order_by(func.sum(Transaction.amount).desc())
    )

    if start_date:
        query = query.where(Transaction.date >= start_date)
    if end_date:
        query = query.where(Transaction.date <= end_date)

    result = await db.execute(query)
    merged: dict[str, dict] = {}
    for row in result.all():
        cat = normalize_category(row.category or "Uncategorized")
        if cat in merged:
            merged[cat]["total"] += row.total
            merged[cat]["count"] += row.count
        else:
            merged[cat] = {"total": row.total, "count": row.count}
    return sorted(
        [CategorySummary(category=k, total=round(v["total"], 2), count=v["count"]) for k, v in merged.items()],
        key=lambda x: x.total,
        reverse=True,
    )


@router.get("/monthly-trend", response_model=list[MonthlyTrend])
async def get_monthly_trend(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    months: int = Query(6, ge=1, le=24),
):
    from app.services.analytics_service import TRANSFER_CATEGORIES, _is_cc_payment

    effective_category = effective_category_expr()
    cutoff = date.today().replace(day=1) - timedelta(days=(months - 1) * 31)
    cutoff = cutoff.replace(day=1)

    result = await db.execute(
        select(Transaction.date, Transaction.amount)
        .join(Account, Transaction.account_id == Account.id)
        .where(
            Account.user_id == current_user.id,
            Transaction.date >= cutoff,
            or_(
                effective_category.is_(None),
                effective_category.notin_(TRANSFER_CATEGORIES),
            ),
            ~_is_cc_payment(),
        )
    )

    # Bucket by month
    buckets: dict[str, dict] = {}
    for row in result.all():
        month_key = row.date.strftime("%Y-%m")
        if month_key not in buckets:
            buckets[month_key] = {"income": 0.0, "expenses": 0.0}
        if row.amount > 0:
            buckets[month_key]["expenses"] += row.amount
        else:
            buckets[month_key]["income"] += abs(row.amount)

    return sorted(
        [
            MonthlyTrend(
                month=k,
                income=round(v["income"], 2),
                expenses=round(v["expenses"], 2),
                net=round(v["income"] - v["expenses"], 2),
            )
            for k, v in buckets.items()
        ],
        key=lambda x: x.month,
    )
