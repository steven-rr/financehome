import uuid
from datetime import date

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel
from sqlalchemy import Select, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.models.account import Account
from app.models.transaction import Transaction
from app.models.user import User
from app.routers.auth import get_current_user

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
    date: date
    description: str
    merchant_name: str | None
    amount: float
    category: str


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
        query = query.where(Transaction.category == category)
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

    return PaginatedTransactions(
        items=[TransactionResponse.model_validate(t) for t in transactions],
        total=total,
        page=page,
        per_page=per_page,
        pages=(total + per_page - 1) // per_page if total > 0 else 0,
    )


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
            func.coalesce(Transaction.category, Transaction.ai_category).is_(None),
            func.coalesce(Transaction.category, Transaction.ai_category).notin_(TRANSFER_CATEGORIES),
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
            func.coalesce(Transaction.category, Transaction.ai_category).is_(None),
            func.coalesce(Transaction.category, Transaction.ai_category).notin_(TRANSFER_CATEGORIES),
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
            Transaction.date, Transaction.description, Transaction.merchant_name,
            Transaction.amount,
            func.coalesce(Transaction.category, Transaction.ai_category).label("effective_category"),
        )
        .join(Account, Transaction.account_id == Account.id)
        .where(Account.user_id == current_user.id)
        .where(Transaction.amount > 0)
        .where(or_(
            func.coalesce(Transaction.category, Transaction.ai_category).is_(None),
            func.coalesce(Transaction.category, Transaction.ai_category).notin_(TRANSFER_CATEGORIES),
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
            date=row.date,
            description=row.description,
            merchant_name=row.merchant_name,
            amount=round(row.amount, 2),
            category=row.effective_category or "Uncategorized",
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

    effective_category = func.coalesce(Transaction.category, Transaction.ai_category)
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
    rows = result.all()

    return [
        CategorySummary(category=row.category or "Uncategorized", total=round(row.total, 2), count=row.count)
        for row in rows
    ]
