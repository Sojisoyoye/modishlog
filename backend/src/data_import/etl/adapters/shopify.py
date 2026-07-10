"""Shopify CSV adapter — Phase 1 work unit.

Maps Shopify's orders/products CSV export column names to ModishLog field
names. Notably `Option1 Name`/`Option1 Value` (and Option2/Option3) need to
collapse into `product_variants` rows with an `attributes` map.

Shopify's products export represents one product + all of its variants as
*multiple* CSV rows sharing the same `Handle`: the first row in a Handle
group carries the full product info (Title, Body (HTML), Vendor, Product
Category, ...); every subsequent row for that Handle only has variant-level
columns filled in (product columns come back blank). The ETL pipeline maps
the very same uploaded file twice — once as the "products" entity, once as
"product_variants" — so this adapter behaves differently depending on which
`entity` it's asked to map:

- "products": one product row per Handle group (continuation rows are
  dropped by `map_rows` so we don't emit duplicate `source_id`s, which the
  validator treats as an error).
- "product_variants": one variant row per *CSV* row, keyed off Option1/2/3
  Name+Value pairs, with `product_source_id` set to the shared Handle.
- "product_categories": one category row per Handle's `Product Category`.
- "suppliers": one supplier row per Handle's `Vendor`.
- "sales" / "customers": mapped from an orders export (`Name`, `Email`,
  `Lineitem sku`, ...).

Rows that can't produce a usable category/supplier/customer (blank `Product
Category`/`Vendor`/`Email` — common in real Shopify catalogs, since none of
those columns are required by Shopify itself) are skipped rather than
raising: `map_rows` filters them out before they ever reach the validator, so
one row missing an optional column doesn't abort the whole import job for
every other entity in the same upload.
"""

from collections.abc import Iterable

from src.data_import.etl.adapters.base import BaseCSVAdapter

_CHANNEL = "online"  # Shopify orders are (almost) always placed online.


class ShopifyCSVAdapter(BaseCSVAdapter):
    def map_rows(
        self, entity: str, rows: list[dict[str, str]]
    ) -> list[dict[str, str]]:
        if entity == "products":
            return self._map_product_rows(rows)
        mapped = [self.map_row(entity, row, index=i) for i, row in enumerate(rows, start=1)]
        if entity in ("product_categories", "suppliers", "customers"):
            # These entities are optional per-row (a product row is free to
            # have no Vendor/Product Category, an order row is free to have
            # no Email) — skip what can't be mapped instead of failing the
            # whole upload for one incomplete row. They're also frequently
            # *repeated* across rows (many products share one Vendor/
            # Category, an order's line items repeat the same Email) — the
            # validator treats a repeated source_id within one upload as an
            # error, so dedupe by source_id here too.
            mapped = _dedupe_by_source_id(row for row in mapped if row)
        return mapped

    def _map_product_rows(self, rows: list[dict[str, str]]) -> list[dict[str, str]]:
        """One product per Handle — the first row seen for a given Handle
        wins; later rows in the same group are variant-only continuation
        rows and are dropped here (they carry no new product info, and
        emitting them would produce duplicate `source_id`s for the products
        entity, which the validator rejects).
        """
        seen_handles: set[str] = set()
        out: list[dict[str, str]] = []
        for row in rows:
            handle = (row.get("Handle") or "").strip()
            if not handle or handle in seen_handles:
                continue
            if not (row.get("Title") or "").strip():
                # Continuation row for a Handle we haven't seen a full
                # product row for yet (e.g. out-of-order export) — nothing
                # usable to build a product from.
                continue
            seen_handles.add(handle)
            out.append(self.map_row("products", row))
        return out

    def map_row(
        self, entity: str, raw_row: dict[str, str], index: int = 1
    ) -> dict[str, str]:
        """`index` (an extension beyond the base 2-arg interface) disambiguates
        `product_variants` `source_id`s for rows with a blank Variant SKU —
        `map_rows()` always threads a unique per-row index through it.
        Calling `map_row("product_variants", row)` directly, without going
        through `map_rows`, is only safe one row at a time: two separate
        direct calls for blank-SKU rows of the *same* Handle will both fall
        back to `index=1` and collide on `source_id`.
        """
        if entity == "products":
            return self._map_product(raw_row)
        if entity == "product_variants":
            return self._map_variant(raw_row, index)
        if entity == "product_categories":
            return self._map_category(raw_row)
        if entity == "suppliers":
            return self._map_supplier(raw_row)
        if entity == "customers":
            return self._map_customer(raw_row)
        if entity == "sales":
            return self._map_sale(raw_row)
        raise ValueError(f"ShopifyCSVAdapter: unsupported entity {entity!r}")

    # ------------------------------------------------------------------
    # Products export
    # ------------------------------------------------------------------

    def _map_product(self, row: dict[str, str]) -> dict[str, str]:
        handle = (row.get("Handle") or "").strip()
        category = (row.get("Product Category") or "").strip()
        return {
            "source_id": handle,
            "name": (row.get("Title") or "").strip(),
            "sku": (row.get("Variant SKU") or "").strip(),
            "barcode": (row.get("Variant Barcode") or "").strip(),
            # Shopify's export has no cost-of-goods column — "0" (not "")
            # matches transform_products' own fallback and keeps
            # normalize_amount() from raising on an empty string.
            "unit_cost": "0",
            "selling_price": (row.get("Variant Price") or "").strip(),
            "currency": "NGN",
            "category_source_id": category,
            "is_active": _is_published(row.get("Published")),
        }

    def _map_category(self, row: dict[str, str]) -> dict[str, str]:
        category = (row.get("Product Category") or "").strip()
        if not category:
            # No category on this product row — map_rows() filters this
            # empty dict out rather than raising, so one row without a
            # category doesn't abort the whole categories/products/variants
            # upload.
            return {}
        return {
            "source_id": category,
            "name": category,
            "description": "",
            "parent_source_id": "",
        }

    def _map_supplier(self, row: dict[str, str]) -> dict[str, str]:
        vendor = (row.get("Vendor") or "").strip()
        if not vendor:
            # No vendor on this product row — see _map_category's note.
            return {}
        return {
            "source_id": vendor,
            "name": vendor,
            "email": (row.get("Email") or "").strip(),
            "contact_person": "",
            "mobile": "",
        }

    # ------------------------------------------------------------------
    # Variants — one per CSV row, grouped by Handle via product_source_id
    # ------------------------------------------------------------------

    def _map_variant(self, row: dict[str, str], index: int) -> dict[str, str]:
        handle = (row.get("Handle") or "").strip()
        sku = (row.get("Variant SKU") or "").strip()
        variant_key = sku or str(index)

        attributes = _build_attributes(row)
        name_parts = [v for _, v in _option_pairs(row)]
        name = " / ".join(name_parts) if name_parts else (row.get("Title") or "").strip()

        return {
            "source_id": f"{handle}-{variant_key}",
            "product_source_id": handle,
            "name": name,
            "sku": sku,
            "barcode": (row.get("Variant Barcode") or "").strip(),
            "attributes": attributes,
            "price_override": (row.get("Variant Price") or "").strip(),
            "cost_price_override": "",
        }

    # ------------------------------------------------------------------
    # Orders export
    # ------------------------------------------------------------------

    def _map_customer(self, row: dict[str, str]) -> dict[str, str]:
        email = (row.get("Email") or "").strip()
        if not email:
            # Guest/no-email order row — see _map_category's note.
            return {}
        return {
            "source_id": email,
            "name": email,
            "email": email,
            "contact_number": "",
        }

    def _map_sale(self, row: dict[str, str]) -> dict[str, str]:
        sku = (row.get("Lineitem sku") or "").strip()
        email = (row.get("Email") or "").strip()
        return {
            "product_source_id": sku,
            "variant_source_id": sku,
            "customer_source_id": email,
            "quantity": (row.get("Lineitem quantity") or "").strip(),
            "unit_price": (row.get("Lineitem price") or "").strip(),
            "sale_date": _shopify_date(row.get("Created at")),
            "currency": (row.get("Currency") or "").strip() or "NGN",
            "channel": _CHANNEL,
            "payment_method": "",
            "location_name": "",
        }


def _dedupe_by_source_id(rows: Iterable[dict[str, str]]) -> list[dict[str, str]]:
    """Keep the first row seen per `source_id`. The validator treats a
    repeated `source_id` within one entity's upload as an error, so this
    guards against the same Vendor/Category/Email showing up on many rows
    of the same underlying Shopify export.
    """
    seen: set[str] = set()
    out: list[dict[str, str]] = []
    for row in rows:
        source_id = row.get("source_id")
        if source_id in seen:
            continue
        seen.add(source_id)
        out.append(row)
    return out


def _is_published(raw: str | None) -> str:
    return "true" if (raw or "").strip().lower() == "true" else "false"


def _shopify_date(raw: str | None) -> str:
    """Shopify's order export timestamps look like
    `2026-06-01 10:15:00 -0400` — `parse_flexible_date` (extractor.py) only
    understands bare dates/times, not a trailing UTC offset, so trim to the
    `YYYY-MM-DD` prefix here rather than touch the shared extractor.
    """
    value = (raw or "").strip()
    return value[:10] if value else ""


def _option_pairs(row: dict[str, str]) -> list[tuple[str, str]]:
    pairs = []
    for n in (1, 2, 3):
        name = (row.get(f"Option{n} Name") or "").strip()
        value = (row.get(f"Option{n} Value") or "").strip()
        if name and value:
            pairs.append((name, value))
    return pairs


def _build_attributes(row: dict[str, str]) -> str:
    return ";".join(f"{name.lower()}:{value}" for name, value in _option_pairs(row))
