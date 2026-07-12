"""Shared SQLAlchemy WHERE-clause helpers used across domain services."""

import uuid

from sqlalchemy import ColumnElement, or_
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
