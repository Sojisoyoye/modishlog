"""Validate layer — dry-run structural checks over raw rows, before any DB write.

Runs independently of the transformer's dedup/ghost-record warnings; the
service layer merges both lists before deciding whether a job can move to
`awaiting_confirmation` (zero errors — warnings are fine).
"""

from src.data_import.etl.extractor import parse_flexible_amount, parse_flexible_date
from src.data_import.schemas import ValidationIssue

# entity -> rules: required/dates/amounts/positive_amounts are field-name
# tuples; unique_source_id is a bool (defaults True — see validate_entity_rows).
ENTITY_RULES: dict[str, dict[str, tuple[str, ...] | bool]] = {
    "product_categories": {"required": ("name",), "dates": (), "amounts": ()},
    "products": {
        "required": ("name",),
        "dates": (),
        "amounts": ("unit_cost", "selling_price"),
    },
    "product_variants": {
        "required": ("name", "product_source_id"),
        "dates": (),
        "amounts": (),
    },
    "customers": {"required": ("name",), "dates": (), "amounts": ()},
    "suppliers": {"required": ("name",), "dates": (), "amounts": ()},
    "business_locations": {"required": ("name",), "dates": (), "amounts": ()},
    "sales": {
        "required": ("product_source_id", "quantity", "unit_price", "sale_date"),
        "dates": ("sale_date",),
        "amounts": ("unit_price",),
    },
    "purchase_orders": {
        "required": ("product_source_id", "quantity", "unit_cost"),
        "dates": ("order_date",),
        "amounts": (),
        # Stricter than "amounts" (>= 0) — OrderLineItemCreate requires
        # quantity/unit_cost to be strictly positive (Field(..., gt=0)); a
        # zero value here would otherwise pass validation clean and only
        # blow up as a raw pydantic error inside load_purchase_orders() at
        # confirm time, rolling back the whole import. fx_rate is optional
        # (not in "required") but, like quantity/unit_cost, must still be a
        # genuine positive amount when present — transform_purchase_orders()
        # parses it inside the same try/except as quantity/unit_cost/
        # order_date, so an unvalidated garbage value (not just a missing
        # one) would silently drop the entire otherwise-valid line item at
        # confirm time as a generic "could not parse row" error, with
        # nothing pointing at fx_rate as the actual cause.
        "positive_amounts": ("quantity", "unit_cost", "fx_rate"),
        # transform_purchase_orders() does int(normalize_amount(...)) on
        # quantity — a fractional value (e.g. "10.7") would silently lose
        # its remainder at confirm time with no trace of the discrepancy.
        # Reject it here instead, while the row can still be corrected.
        "integer_amounts": ("quantity",),
        # Rows sharing the same source_id are one multi-line-item order by
        # design (see transform_purchase_orders) — not a duplicate.
        "unique_source_id": False,
    },
    "expense_categories": {"required": ("name",), "dates": (), "amounts": ()},
    "expenses": {
        "required": ("amount", "expense_date"),
        "dates": ("expense_date",),
        "amounts": (),
        "positive_amounts": ("amount",),
    },
    "stock_adjustments": {
        "required": ("product_source_id", "quantity_change"),
        "dates": ("adjustment_date",),
        # quantity_change may legitimately be negative (e.g. damaged/lost
        # stock) — neither "amounts" (rejects <0) nor "positive_amounts"
        # (rejects <=0) fits, so it's only integer-checked, not sign-checked.
        "amounts": (),
        "integer_amounts": ("quantity_change",),
        # Rows sharing the same source_id are one multi-product adjustment
        # with multiple lines by design (see _map_stock_adjustments /
        # transform_stock_adjustments) — not a duplicate. Same reasoning as
        # purchase_orders above.
        "unique_source_id": False,
    },
    "sell_returns": {
        "required": ("sale_source_id", "total_amount", "return_date"),
        "dates": ("return_date",),
        "amounts": (),
        "positive_amounts": ("total_amount",),
    },
    "purchase_returns": {
        "required": ("purchase_source_id", "total_amount", "return_date"),
        "dates": ("return_date",),
        "amounts": (),
        "positive_amounts": ("total_amount",),
    },
}


def _check_amount(
    entity: str, row: int, data: dict, field: str, *, require_positive: bool
) -> list[ValidationIssue]:
    value = data.get(field)
    if not value:
        return []
    try:
        amount = parse_flexible_amount(value)
    except Exception:
        return [
            ValidationIssue(
                entity=entity,
                row=row,
                field=field,
                severity="error",
                message=f"Not a numeric amount: {value!r}",
            )
        ]
    if require_positive and amount <= 0:
        return [
            ValidationIssue(
                entity=entity,
                row=row,
                field=field,
                severity="error",
                message=f"{field} must be greater than zero",
            )
        ]
    if not require_positive and amount < 0:
        return [
            ValidationIssue(
                entity=entity,
                row=row,
                field=field,
                severity="error",
                message=f"{field} cannot be negative",
            )
        ]
    return []


def _check_integer(
    entity: str, row: int, data: dict, field: str
) -> list[ValidationIssue]:
    value = data.get(field)
    if not value:
        return []
    try:
        amount = parse_flexible_amount(value)
    except Exception:
        return []  # already reported by the amounts/positive_amounts check
    if amount != amount.to_integral_value():
        return [
            ValidationIssue(
                entity=entity,
                row=row,
                field=field,
                severity="error",
                message=f"{field} must be a whole number, got {value!r}",
            )
        ]
    return []


def validate_entity_rows(entity: str, rows: list[dict]) -> list[ValidationIssue]:
    rules = ENTITY_RULES.get(entity)
    if rules is None:
        return []

    issues: list[ValidationIssue] = []
    seen_source_ids: set[str] = set()

    for i, row in enumerate(rows, start=2):  # row 1 is the header
        for field in rules["required"]:
            if not (row.get(field) or "").strip():
                issues.append(
                    ValidationIssue(
                        entity=entity,
                        row=i,
                        field=field,
                        severity="error",
                        message=f"{field} is required",
                    )
                )

        for field in rules["dates"]:
            value = row.get(field)
            if value:
                try:
                    parse_flexible_date(value)
                except ValueError:
                    issues.append(
                        ValidationIssue(
                            entity=entity,
                            row=i,
                            field=field,
                            severity="error",
                            message=f"Unrecognised date: {value!r}",
                        )
                    )

        for field in rules["amounts"]:
            issues.extend(_check_amount(entity, i, row, field, require_positive=False))

        for field in rules.get("positive_amounts", ()):
            issues.extend(_check_amount(entity, i, row, field, require_positive=True))

        for field in rules.get("integer_amounts", ()):
            issues.extend(_check_integer(entity, i, row, field))

        source_id = row.get("source_id")
        if source_id and rules.get("unique_source_id", True):
            if source_id in seen_source_ids:
                issues.append(
                    ValidationIssue(
                        entity=entity,
                        row=i,
                        field="source_id",
                        severity="error",
                        message=f"Duplicate source_id {source_id!r} within this upload",
                    )
                )
            seen_source_ids.add(source_id)

    return issues


def validate_extracted_data(extracted: dict[str, list[dict]]) -> list[ValidationIssue]:
    issues: list[ValidationIssue] = []
    for entity, rows in extracted.items():
        issues.extend(validate_entity_rows(entity, rows))
    return issues
