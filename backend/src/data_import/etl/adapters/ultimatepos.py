"""UltimatePOS CSV adapter — Phase 1 work unit.

Maps UltimatePOS's CSV export column names to ModishLog field names. See
`backend/scripts/pos_migrate.py` for the field names UltimatePOS uses in its
live API (`variation_id`, `sell_price_inc_tax`, `tax_amount`,
`discount_amount`, `product`, `sku`, `selling_price`, `max_price`,
`current_stock`, contact fields like `name`/`mobile`/`email`, ...).

UltimatePOS's CSV *export* generally reuses the same underlying field
vocabulary as its API, but different report/version combinations title-case
and space column headers differently (e.g. "Product Name" vs `product`,
"Sub SKU" vs `sub_sku`). Real-world UltimatePOS exports are not perfectly
consistent across versions, so `map_row` is deliberately tolerant: for every
target field we try a list of known header aliases (snake_case API-style
first, then the common title-case export spellings) and take the first
present key. This is a pragmatic best-effort mapping, not a guarantee that
every possible UltimatePOS export variant is covered — ambiguous cases are
called out per-entity below.
"""

from src.data_import.etl.adapters.base import BaseCSVAdapter


def _first(row: dict[str, str], *keys: str) -> str | None:
    """Return the value of the first key present in ``row`` (regardless of
    emptiness), or None if none of the keys exist at all.
    """
    for key in keys:
        if key in row:
            return row[key]
    return None


def _first_required(row: dict[str, str], *keys: str) -> str:
    value = _first(row, *keys)
    if value is None:
        raise KeyError(
            f"None of the expected UltimatePOS columns {keys!r} were found in row {row!r}"
        )
    return value


def _first_or_default(row: dict[str, str], default: str, *keys: str) -> str:
    value = _first(row, *keys)
    return default if value is None else value


class UltimatePOSCSVAdapter(BaseCSVAdapter):
    def map_row(self, entity: str, raw_row: dict[str, str]) -> dict[str, str]:
        handler = _ENTITY_HANDLERS.get(entity)
        if handler is None:
            # Unknown/unmapped entity — pass through unchanged, same as the
            # generic adapter, so upstream validation can flag it rather than
            # this adapter silently dropping data.
            return raw_row
        return handler(raw_row)


# ---------------------------------------------------------------------------
# Per-entity mapping functions
# ---------------------------------------------------------------------------


def _map_product_category(row: dict[str, str]) -> dict[str, str]:
    return {
        "source_id": _first_required(row, "id", "Category ID", "category_id"),
        "name": _first_required(row, "name", "Category Name", "category"),
        "description": _first_or_default(row, "", "description", "Description", "short_code"),
        "parent_source_id": _first_or_default(
            row, "", "parent_id", "Parent Category ID", "parent_category_id"
        ),
    }


def _map_product(row: dict[str, str]) -> dict[str, str]:
    is_inactive_raw = _first_or_default(
        row, "0", "is_inactive", "Is Inactive", "not_for_selling"
    )
    is_active = str(is_inactive_raw).strip().lower() not in ("1", "true", "yes")

    return {
        "source_id": _first_required(row, "id", "Product ID", "product_id"),
        "name": _first_required(row, "product", "Product Name", "name"),
        "sku": _first_or_default(row, "", "sku", "SKU"),
        "barcode": _first_or_default(row, "", "barcode", "Barcode"),
        # UltimatePOS hides supplier cost on most plans; `purchase_price` /
        # "Purchase Price" is the closest available field for unit_cost.
        "unit_cost": _first_or_default(
            row, "0", "purchase_price", "Purchase Price", "default_purchase_price", "max_price"
        ),
        "selling_price": _first_or_default(
            row, "0", "selling_price", "Selling Price", "default_sell_price"
        ),
        "currency": _first_or_default(row, "NGN", "currency", "Currency"),
        # Deliberately excludes UltimatePOS's `category`/"Category" columns —
        # those hold a human-readable category *name* (see
        # `pos_migrate.py`'s `p.get("category", "")`), not an id. Mapping a
        # name string into `category_source_id` would silently produce a
        # reference the transformer can never resolve against
        # `product_categories.source_id`.
        "category_source_id": _first_or_default(row, "", "category_id", "Category ID"),
        "is_active": "true" if is_active else "false",
    }


def _map_product_variant(row: dict[str, str]) -> dict[str, str]:
    # Attribute columns are the ambiguous part of UltimatePOS variant exports:
    # different report versions emit either a single "Variation Name" (e.g.
    # "Blue / Large") or up to N pairs of
    # `variation_value_{n}_name`/`variation_value_{n}` columns. We prefer the
    # structured pairs (they round-trip cleanly into "key:value;..." pairs)
    # and fall back to a single "Attribute"/"Variation" column tagged under a
    # generic "Variation" key when structured pairs aren't present.
    pairs: list[tuple[str, str]] = []
    i = 1
    while True:
        name_key_candidates = (f"variation_value_{i}_name", f"Variation {i} Name")
        value_key_candidates = (f"variation_value_{i}", f"Variation {i} Value")
        attr_name = _first(row, *name_key_candidates)
        attr_value = _first(row, *value_key_candidates)
        if attr_name is None and attr_value is None:
            break
        if attr_name and attr_value:
            pairs.append((attr_name, attr_value))
        i += 1

    if not pairs:
        single_value = _first(row, "attribute_value", "Attribute Value", "sub_type")
        if single_value:
            pairs.append(("Variation", single_value))

    attributes = ";".join(f"{k}:{v}" for k, v in pairs)

    return {
        "source_id": _first_required(row, "variation_id", "Variation ID"),
        "product_source_id": _first_required(row, "product_id", "Product ID"),
        "name": _first_required(row, "name", "Variation Name", "sub_type"),
        "sku": _first_or_default(row, "", "sub_sku", "Sub SKU", "sku"),
        "barcode": _first_or_default(row, "", "sub_barcode", "Sub Barcode", "barcode"),
        "attributes": attributes,
        "price_override": _first_or_default(
            row, "", "sell_price_inc_tax", "Sell Price Inc Tax", "default_sell_price"
        ),
        "cost_price_override": _first_or_default(
            row, "", "default_purchase_price", "Default Purchase Price", "purchase_price"
        ),
    }


def _map_supplier(row: dict[str, str]) -> dict[str, str]:
    # UltimatePOS "supplier" is a `contacts` row with `type=supplier`. The
    # business/company name (if present) is more useful as `contact_person`
    # context than as the primary `name` — the individual/contact `name`
    # field stays the row's `name`.
    return {
        "source_id": _first_required(row, "id", "Contact ID", "contact_id"),
        "name": _first_required(row, "name", "Supplier Name", "Contact Name"),
        "email": _first_or_default(row, "", "email", "Email"),
        "contact_person": _first_or_default(
            row, "", "supplier_business_name", "Business Name", "contact_person"
        ),
        "mobile": _first_or_default(row, "", "mobile", "Mobile", "contact_no"),
    }


def _map_customer(row: dict[str, str]) -> dict[str, str]:
    return {
        "source_id": _first_required(row, "id", "Contact ID", "contact_id"),
        "name": _first_required(row, "name", "Customer Name", "Contact Name"),
        "email": _first_or_default(row, "", "email", "Email"),
        "contact_number": _first_or_default(row, "", "mobile", "Mobile", "contact_no"),
    }


def _map_business_location(row: dict[str, str]) -> dict[str, str]:
    return {
        "source_id": _first_required(row, "id", "Location ID", "business_location_id"),
        "name": _first_required(row, "name", "Location Name"),
        "location_code": _first_or_default(row, "", "location_id", "Location Code"),
    }


_SALE_TYPE_MAP = {
    "pos": "retail",
    "retail": "retail",
    "in_store": "retail",
    "in-store": "retail",
    "online": "online",
    "wholesale": "wholesale",
}


def _map_sale(row: dict[str, str]) -> dict[str, str]:
    raw_channel = _first(row, "sale_type", "Sale Type", "channel", "Channel")
    channel = _SALE_TYPE_MAP.get((raw_channel or "").strip().lower(), "retail")

    return {
        "product_source_id": _first_required(row, "product_id", "Product ID"),
        "variant_source_id": _first_or_default(row, "", "variation_id", "Variation ID"),
        "customer_source_id": _first_or_default(row, "", "contact_id", "Contact ID"),
        "quantity": _first_required(row, "quantity", "Quantity"),
        # UltimatePOS exposes both tax-inclusive and exclusive unit price
        # columns; tax-inclusive is what the customer actually paid per unit,
        # so it's the closest match to ModishLog's single `unit_price` field.
        "unit_price": _first_required(
            row, "unit_price_inc_tax", "Unit Price Inc Tax", "unit_price", "Unit Price"
        ),
        "sale_date": _first_required(row, "transaction_date", "Transaction Date", "sale_date"),
        "currency": _first_or_default(row, "NGN", "currency", "Currency"),
        "channel": channel,
        "payment_method": _first_or_default(
            row, "", "payment_type", "Payment Type", "payment_method"
        ),
        "location_name": _first_or_default(
            row, "", "location_name", "Location Name", "business_location"
        ),
    }


_ENTITY_HANDLERS = {
    "product_categories": _map_product_category,
    "products": _map_product,
    "product_variants": _map_product_variant,
    "suppliers": _map_supplier,
    "customers": _map_customer,
    "business_locations": _map_business_location,
    "sales": _map_sale,
}
