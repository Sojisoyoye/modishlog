import csv
import io
import uuid
from datetime import date

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from src.expenses.exceptions import ExpenseNotFoundError
from src.expenses.models import Expense, ExpenseCategory
from src.expenses.schemas import ExpenseCategoryCreate, ExpenseCreate, ExpenseUpdate


async def create_category(
    db: AsyncSession, data: ExpenseCategoryCreate, user_id: uuid.UUID
) -> ExpenseCategory:
    cat = ExpenseCategory(
        name=data.name,
        description=data.description,
        created_by=user_id,
    )
    db.add(cat)
    await db.flush()
    return cat


async def list_categories(db: AsyncSession) -> list[ExpenseCategory]:
    result = await db.execute(
        select(ExpenseCategory).order_by(ExpenseCategory.name)
    )
    return result.scalars().all()


async def create_expense(
    db: AsyncSession, data: ExpenseCreate, user_id: uuid.UUID
) -> Expense:
    exp = Expense(
        category_id=data.category_id,
        ref_no=data.ref_no,
        amount_ngn=data.amount_ngn,
        fx_rate=data.fx_rate,
        amount_usd=data.amount_usd,
        currency=data.currency,
        expense_date=data.expense_date,
        payment_method=data.payment_method,
        note=data.note,
        location_id=data.location_id,
        created_by=user_id,
    )
    db.add(exp)
    await db.flush()
    return await get_expense(db, exp.id)


async def list_expenses(
    db: AsyncSession,
    *,
    category_id: uuid.UUID | None = None,
    date_from: date | None = None,
    date_to: date | None = None,
    page: int = 1,
    page_size: int = 25,
) -> tuple[list[Expense], int]:
    base_q = select(Expense)
    if category_id is not None:
        base_q = base_q.where(Expense.category_id == category_id)
    if date_from is not None:
        base_q = base_q.where(Expense.expense_date >= date_from)
    if date_to is not None:
        base_q = base_q.where(Expense.expense_date <= date_to)

    count_result = await db.execute(
        select(func.count()).select_from(base_q.subquery())
    )
    total = count_result.scalar()

    items_result = await db.execute(
        base_q.options(selectinload(Expense.category))
        .order_by(Expense.expense_date.desc(), Expense.created_at.desc())
        .offset((page - 1) * page_size)
        .limit(page_size)
    )
    return items_result.scalars().all(), total


async def get_expense(db: AsyncSession, expense_id: uuid.UUID) -> Expense:
    result = await db.execute(
        select(Expense)
        .options(selectinload(Expense.category))
        .where(Expense.id == expense_id)
    )
    exp = result.scalar_one_or_none()
    if exp is None:
        raise ExpenseNotFoundError(expense_id)
    return exp


async def update_expense(
    db: AsyncSession, expense_id: uuid.UUID, data: ExpenseUpdate
) -> Expense:
    exp = await get_expense(db, expense_id)
    for field, value in data.model_dump(exclude_unset=True).items():
        setattr(exp, field, value)
    await db.flush()
    return await get_expense(db, expense_id)


async def delete_expense(db: AsyncSession, expense_id: uuid.UUID) -> None:
    exp = await get_expense(db, expense_id)
    db.delete(exp)
    await db.flush()


async def export_expenses_csv(
    db: AsyncSession,
    *,
    date_from: date | None = None,
    date_to: date | None = None,
) -> str:
    items, _ = await list_expenses(
        db, date_from=date_from, date_to=date_to, page=1, page_size=100_000
    )
    buf = io.StringIO()
    writer = csv.writer(buf)
    writer.writerow(
        [
            "expense_date",
            "ref_no",
            "category",
            "amount_ngn",
            "fx_rate",
            "amount_usd",
            "currency",
            "payment_method",
            "note",
        ]
    )
    for exp in items:
        writer.writerow(
            [
                exp.expense_date,
                exp.ref_no or "",
                exp.category.name if exp.category else "",
                exp.amount_ngn,
                exp.fx_rate or "",
                exp.amount_usd,
                exp.currency,
                exp.payment_method or "",
                exp.note or "",
            ]
        )
    return buf.getvalue()
