import uuid
from datetime import date

from fastapi import APIRouter, Depends, HTTPException, Query, Response
from sqlalchemy.ext.asyncio import AsyncSession

from src.auth.dependencies import get_current_active_user
from src.auth.models import User
from src.core.database import get_db
from src.expenses.exceptions import ExpenseNotFoundError
from src.expenses.schemas import (
    ExpenseCategoryCreate,
    ExpenseCategoryRead,
    ExpenseCreate,
    ExpenseListResponse,
    ExpenseRead,
    ExpenseUpdate,
)
from src.expenses import service

categories_router = APIRouter(dependencies=[Depends(get_current_active_user)])
expenses_router = APIRouter(dependencies=[Depends(get_current_active_user)])


# ---------------------------------------------------------------------------
# Categories
# ---------------------------------------------------------------------------


@categories_router.post("", response_model=ExpenseCategoryRead, status_code=201)
async def create_category(
    data: ExpenseCategoryCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    cat = await service.create_category(db, data, current_user.id)
    return cat


@categories_router.get("", response_model=list[ExpenseCategoryRead])
async def list_categories(db: AsyncSession = Depends(get_db)):
    return await service.list_categories(db)


# ---------------------------------------------------------------------------
# Expenses — static routes BEFORE parameterized
# ---------------------------------------------------------------------------


@expenses_router.post("", response_model=ExpenseRead, status_code=201)
async def create_expense(
    data: ExpenseCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    exp = await service.create_expense(db, data, current_user.id)
    return _to_read(exp)


@expenses_router.get("", response_model=ExpenseListResponse)
async def list_expenses(
    category_id: uuid.UUID | None = Query(None),
    date_from: date | None = Query(None),
    date_to: date | None = Query(None),
    page: int = Query(1, ge=1),
    page_size: int = Query(25, ge=1, le=200),
    db: AsyncSession = Depends(get_db),
):
    items, total = await service.list_expenses(
        db,
        category_id=category_id,
        date_from=date_from,
        date_to=date_to,
        page=page,
        page_size=page_size,
    )
    return ExpenseListResponse(
        items=[_to_read(e) for e in items],
        total=total,
        page=page,
        page_size=page_size,
    )


@expenses_router.get("/export")
async def export_expenses_csv(
    date_from: date | None = Query(None),
    date_to: date | None = Query(None),
    db: AsyncSession = Depends(get_db),
):
    csv_str = await service.export_expenses_csv(db, date_from=date_from, date_to=date_to)
    return Response(
        content=csv_str,
        media_type="text/csv",
        headers={"Content-Disposition": "attachment; filename=expenses.csv"},
    )


@expenses_router.get("/{expense_id}", response_model=ExpenseRead)
async def get_expense(expense_id: uuid.UUID, db: AsyncSession = Depends(get_db)):
    try:
        exp = await service.get_expense(db, expense_id)
    except ExpenseNotFoundError:
        raise HTTPException(status_code=404, detail="Expense not found")
    return _to_read(exp)


@expenses_router.put("/{expense_id}", response_model=ExpenseRead)
async def update_expense(
    expense_id: uuid.UUID,
    data: ExpenseUpdate,
    db: AsyncSession = Depends(get_db),
):
    try:
        exp = await service.update_expense(db, expense_id, data)
    except ExpenseNotFoundError:
        raise HTTPException(status_code=404, detail="Expense not found")
    return _to_read(exp)


@expenses_router.delete("/{expense_id}", status_code=204)
async def delete_expense(expense_id: uuid.UUID, db: AsyncSession = Depends(get_db)):
    try:
        await service.delete_expense(db, expense_id)
    except ExpenseNotFoundError:
        raise HTTPException(status_code=404, detail="Expense not found")


# ---------------------------------------------------------------------------
# Internal helper
# ---------------------------------------------------------------------------


def _to_read(exp) -> ExpenseRead:
    r = ExpenseRead.model_validate(exp)
    r.category_name = exp.category.name if exp.category else None
    return r
