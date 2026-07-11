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
        # confirm time, rolling back the whole import.
        "positive_amounts": ("quantity", "unit_cost"),
        # Rows sharing the same source_id are one multi-line-item order by
        # design (see transform_purchase_orders) — not a duplicate.
        "unique_source_id": False,
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
