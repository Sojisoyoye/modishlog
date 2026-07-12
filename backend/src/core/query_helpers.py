"""Shared SQLAlchemy query/mutation helpers used across domain services."""

import uuid
from collections.abc import Collection
from decimal import Decimal

from sqlalchemy import ColumnElement, delete, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import InstrumentedAttribute


def variant_or_untagged_filter(
    variant_column: InstrumentedAttribute, variant_id: uuid.UUID | None
) -> ColumnElement[bool]:
    """WHERE-clause fragment scoping rows to a variant-aware deduction.

    A variant-specific deduction (variant_id given) may draw from that
    variant's own tagged rows AND from untagged (variant_id=NULL) rows —
    stock received before variant tracking existed, or genuinely shared
    stock — but never from a *different* variant's tagged rows, which
    would misattribute that variant's cost/quantity onto this one. A
    non-variant deduction (variant_id=None) only draws from untagged rows.

    Shared by every "variant pools with untagged, never with a sibling"
    consumer — InventoryBatch's fifo_deduct() (task 165) and
    OrderLineItem's _deduct_lot_units() (task 168) — so the rule can't
    silently diverge between the two parallel lot-tracking ledgers.
    """
    if variant_id is not None:
        return or_(variant_column == variant_id, variant_column.is_(None))
    return variant_column.is_(None)


async def reverse_ledger_consumption(
    db: AsyncSession,
    sale_ids: Collection[uuid.UUID],
    *,
    ledger_model: type,
    ledger_sale_id_col: InstrumentedAttribute,
    ledger_target_id_col: InstrumentedAttribute,
    ledger_quantity_col: InstrumentedAttribute,
    target_model: type,
    target_quantity_col: InstrumentedAttribute,
    zero: int | Decimal,
    cast=lambda total: total,
) -> None:
    """Restore `target_quantity_col` on every row a ledger recorded
    `sale_ids` as having consumed, then delete those ledger rows.

    Generic "reverse a per-sale consumption ledger" algorithm shared by
    inventory/service.py's reverse_fifo_consumption() (FifoConsumption ->
    InventoryBatch.quantity_remaining, task 166) and orders/service.py's
    reverse_lot_consumption() (LotConsumption ->
    OrderLineItem.units_remaining, task 170) — both need the exact same
    "sum consumption per target row, bulk-lock the targets, credit back,
    delete the ledger rows" steps; keeping it in one place means a fix to
    the algorithm (e.g. the locking strategy) can't silently apply to only
    one of the two ledgers.
    """
    if not sale_ids:
        return

    result = await db.execute(
        select(ledger_target_id_col, func.sum(ledger_quantity_col))
        .where(ledger_sale_id_col.in_(sale_ids))
        .group_by(ledger_target_id_col)
    )
    deltas = {target_id: cast(total) for target_id, total in result.all()}
    if not deltas:
        return

    # One bulk fetch+lock instead of one SELECT+FOR UPDATE per target_id —
    # a data_import rollback can touch hundreds of sales spread across
    # many targets, and a per-target round-trip there would hold row locks
    # far longer than necessary.
    targets_result = await db.execute(
        select(target_model)
        .where(target_model.id.in_(deltas.keys()))
        .with_for_update()
    )
    quantity_attr = target_quantity_col.key
    for target in targets_result.scalars().all():
        current = getattr(target, quantity_attr)
        setattr(
            target,
            quantity_attr,
            (current if current is not None else zero) + deltas[target.id],
        )

    await db.execute(delete(ledger_model).where(ledger_sale_id_col.in_(sale_ids)))
    await db.flush()
