"""Transform layer — ID remapping, dedup, normalisation, ghost records.

Row shape convention: every raw entity row carries a `source_id` column (the
value the source system used to identify it) so that other entities in the
same upload can reference it via a `<entity>_source_id` column. The
transformer resolves those references into ModishLog UUIDs via `IdMap`.
"""

import uuid
from collections import defaultdict
from decimal import ROUND_HALF_UP, Decimal, InvalidOperation

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from src.customers.models import Customer
from src.data_import.etl.extractor import parse_flexible_amount, parse_flexible_date
from src.data_import.schemas import ValidationIssue
from src.products.models import Product
from src.products.utils import slugify
from src.sales.models import SaleChannel
from src.suppliers.models import Supplier

_CHANNEL_MAP = {
    "online": SaleChannel.ONLINE,
    "retail": SaleChannel.RETAIL,
    "in_store": SaleChannel.RETAIL,
    "in-store": SaleChannel.RETAIL,
    "wholesale": SaleChannel.WHOLESALE,
}


def normalize_channel(raw: str | None) -> SaleChannel:
    return _CHANNEL_MAP.get((raw or "retail").strip().lower(), SaleChannel.RETAIL)


_PAYMENT_METHOD_MAP = {
    "credit card": "card",
    "debit card": "card",
    "card": "card",
    "cash": "cash",
    "bank": "bank_transfer",
    "bank transfer": "bank_transfer",
    "transfer": "bank_transfer",
    "cheque": "cheque",
    "check": "cheque",
    "mobile money": "mobile_money",
    "pos": "card",
}


class IdMap:
    """Per-job registry mapping `(entity, source_id) -> ModishLog UUID`."""

    def __init__(self) -> None:
        self._maps: dict[str, dict[str, uuid.UUID]] = defaultdict(dict)

    def register(self, entity: str, source_id: str, internal_id: uuid.UUID) -> None:
        if not source_id:
            return
        self._maps[entity][source_id] = internal_id

    def lookup(self, entity: str, source_id: str) -> uuid.UUID | None:
        return self._maps[entity].get(source_id)


def normalize_amount(raw: str) -> Decimal:
    return parse_flexible_amount(raw).quantize(
        Decimal("0.000001"), rounding=ROUND_HALF_UP
    )


def normalize_date(raw: str):
    return parse_flexible_date(raw)


def normalize_payment_method(raw: str | None) -> str | None:
    if not raw:
        return None
    return _PAYMENT_METHOD_MAP.get(raw.strip().lower(), "other")


def normalize_name(name: str) -> str:
    return " ".join(name.split()).lower()


class Transformer:
    """Stateful per-job transform pass — holds the id_map and accumulated warnings."""

    def __init__(
        self,
        db: AsyncSession,
        business_id: uuid.UUID,
        created_by: uuid.UUID,
        id_map: IdMap | None = None,
    ) -> None:
        self.db = db
        self.business_id = business_id
        # Every imported row needs an owning user for required created_by /
        # recorded_by columns — attributed to whoever ran the import job.
        self.created_by = created_by
        self.id_map = id_map or IdMap()
        self.warnings: list[ValidationIssue] = []

    def _assign_id(self, entity: str, source_id: str | None) -> uuid.UUID:
        """Pre-assign a UUID for a new row and register it immediately.

        The loader hasn't run yet at transform time, so anything referencing
        this row later in the same job (a child category, a variant, a sale)
        needs an id to resolve against *before* any DB write happens — this
        keeps transform a pure dry-run step, safe to call from validate/
        snapshot without touching the database.
        """
        new_id = uuid.uuid4()
        self.id_map.register(entity, source_id, new_id)
        return new_id

    # ------------------------------------------------------------------
    # Dedup lookups
    # ------------------------------------------------------------------

    async def dedup_customer(
        self, email: str | None, phone: str | None
    ) -> Customer | None:
        if email:
            result = await self.db.execute(
                select(Customer).where(
                    Customer.business_id == self.business_id,
                    func.lower(Customer.email) == email.lower(),
                )
            )
            existing = result.scalar_one_or_none()
            if existing:
                return existing
        if phone:
            result = await self.db.execute(
                select(Customer).where(
                    Customer.business_id == self.business_id,
                    Customer.contact_number == phone,
                )
            )
            existing = result.scalar_one_or_none()
            if existing:
                return existing
        return None

    async def dedup_supplier(self, name: str, email: str | None) -> Supplier | None:
        q = select(Supplier).where(
            Supplier.business_id == self.business_id,
            func.lower(Supplier.name) == name.lower(),
        )
        if email:
            q = q.where(func.lower(Supplier.email) == email.lower())
        result = await self.db.execute(q)
        return result.scalar_one_or_none()

    async def dedup_product(
        self, barcode: str | None, sku: str | None
    ) -> Product | None:
        if barcode:
            # Scoped by business_id like every other dedup lookup — barcode has
            # no global-uniqueness constraint in this schema, so an unscoped
            # match here would leak another business's product into this job's
            # id_map (a cross-tenant data leak, per the isolation invariant
            # from the business_id migration work).
            result = await self.db.execute(
                select(Product).where(
                    Product.business_id == self.business_id, Product.barcode == barcode
                )
            )
            existing = result.scalar_one_or_none()
            if existing:
                return existing
        if sku:
            result = await self.db.execute(
                select(Product).where(
                    Product.business_id == self.business_id, Product.sku == sku
                )
            )
            existing = result.scalar_one_or_none()
            if existing:
                return existing
        return None

    # ------------------------------------------------------------------
    # Entity transforms — each returns normalised dicts ready for the loader
    # ------------------------------------------------------------------

    async def transform_categories(self, raw_rows: list[dict]) -> list[dict]:
        out = []
        for row in raw_rows:
            parent_id = None
            parent_source_id = row.get("parent_source_id")
            if parent_source_id:
                parent_id = self.id_map.lookup("product_categories", parent_source_id)
            source_id = row.get("source_id")
            out.append(
                {
                    "id": self._assign_id("product_categories", source_id),
                    "_source_id": source_id,
                    "name": row["name"].strip(),
                    "description": row.get("description") or None,
                    "parent_id": parent_id,
                    "business_id": self.business_id,
                }
            )
        return out

    async def transform_products(self, raw_rows: list[dict]) -> list[dict]:
        out = []
        for row in raw_rows:
            barcode = row.get("barcode") or None
            sku = row.get("sku") or None
            name = row["name"].strip()
            existing = await self.dedup_product(barcode, sku)
            if existing is not None:
                self.id_map.register("products", row.get("source_id"), existing.id)
                continue

            category_id = None
            category_source_id = row.get("category_source_id")
            if category_source_id:
                category_id = self.id_map.lookup(
                    "product_categories", category_source_id
                )

            source_id = row.get("source_id")
            out.append(
                {
                    "id": self._assign_id("products", source_id),
                    "_source_id": source_id,
                    "name": name,
                    "sku": sku or f"IMPORTED-{uuid.uuid4().hex[:10].upper()}",
                    "slug": slugify(name) or f"product-{uuid.uuid4().hex[:8]}",
                    "barcode": barcode,
                    "unit_cost": normalize_amount(row.get("unit_cost", "0")),
                    "selling_price": normalize_amount(row.get("selling_price", "0")),
                    "currency": row.get("currency", "NGN").upper(),
                    "category_id": category_id,
                    "is_active": row.get("is_active", "true").strip().lower()
                    != "false",
                    "business_id": self.business_id,
                }
            )
        return out

    async def transform_variants(self, raw_rows: list[dict]) -> list[dict]:
        out = []
        for row in raw_rows:
            product_id = self.id_map.lookup("products", row.get("product_source_id"))
            if product_id is None:
                self.warnings.append(
                    ValidationIssue(
                        entity="product_variants",
                        row=0,
                        field="product_source_id",
                        severity="warning",
                        message=f"Variant references unknown product {row.get('product_source_id')!r} — skipped",
                    )
                )
                continue
            source_id = row.get("source_id")
            out.append(
                {
                    "id": self._assign_id("product_variants", source_id),
                    "_source_id": source_id,
                    "product_id": product_id,
                    "name": row["name"].strip(),
                    "sku": row.get("sku") or None,
                    "barcode": row.get("barcode") or None,
                    "attributes": {
                        k: v
                        for k, v in (
                            pair.split(":", 1)
                            for pair in row.get("attributes", "").split(";")
                            if ":" in pair
                        )
                    },
                    "price_override": (
                        normalize_amount(row["price_override"])
                        if row.get("price_override")
                        else None
                    ),
                    "cost_price_override": (
                        normalize_amount(row["cost_price_override"])
                        if row.get("cost_price_override")
                        else None
                    ),
                    "business_id": self.business_id,
                }
            )
        return out

    async def transform_suppliers(self, raw_rows: list[dict]) -> list[dict]:
        out = []
        for row in raw_rows:
            name = row["name"].strip()
            email = row.get("email") or None
            existing = await self.dedup_supplier(name, email)
            if existing is not None:
                self.id_map.register("suppliers", row.get("source_id"), existing.id)
                continue
            source_id = row.get("source_id")
            out.append(
                {
                    "id": self._assign_id("suppliers", source_id),
                    "_source_id": source_id,
                    "name": name,
                    "email": email,
                    "contact_person": row.get("contact_person") or None,
                    "mobile": row.get("mobile") or None,
                    "business_id": self.business_id,
                    "created_by": self.created_by,
                }
            )
        return out

    async def transform_customers(self, raw_rows: list[dict]) -> list[dict]:
        out = []
        for row in raw_rows:
            email = row.get("email") or None
            phone = row.get("contact_number") or None
            existing = await self.dedup_customer(email, phone)
            if existing is not None:
                # No mutation of `existing` here — transform must stay a pure
                # dry-run (validate/snapshot call it without writing to the DB).
                self.id_map.register("customers", row.get("source_id"), existing.id)
                continue
            source_id = row.get("source_id")
            out.append(
                {
                    "id": self._assign_id("customers", source_id),
                    "_source_id": source_id,
                    "name": row["name"].strip(),
                    "email": email,
                    "contact_number": phone,
                    "business_id": self.business_id,
                    "created_by": self.created_by,
                }
            )
        return out

    def transform_locations(self, raw_rows: list[dict]) -> list[dict]:
        out = []
        for row in raw_rows:
            source_id = row.get("source_id")
            out.append(
                {
                    "id": self._assign_id("business_locations", source_id),
                    "_source_id": source_id,
                    "name": row["name"].strip(),
                    "location_code": row.get("location_code")
                    or row["name"][:20].upper(),
                    "business_id": self.business_id,
                    "created_by": self.created_by,
                }
            )
        return out

    def transform_sales(
        self, raw_rows: list[dict], location_map: dict[str, uuid.UUID] | None = None
    ) -> list[dict]:
        location_map = location_map or {}
        out = []
        for i, row in enumerate(raw_rows, start=2):
            product_id = self.id_map.lookup("products", row.get("product_source_id"))
            if product_id is None:
                # detect_ghost_products() should have run first and registered a
                # ghost product for every unresolved reference — this is a bug
                # in the caller's ordering, not bad input, so it's an error.
                self.warnings.append(
                    ValidationIssue(
                        entity="sales",
                        row=i,
                        field="product_source_id",
                        severity="error",
                        message=f"Product {row.get('product_source_id')!r} could not be resolved",
                    )
                )
                continue

            # transform runs before validator.validate_extracted_data (it needs
            # to happen first to populate id_map), so malformed quantity/price
            # values haven't been rejected yet — coerce defensively here rather
            # than let int()/Decimal() raise and crash the whole dry-run.
            #
            # int(normalize_amount(...)), not plain int() — validate_entity_rows()
            # accepts "10.0"/"1,000" for quantity (the same lenient
            # parse_flexible_amount() every other amount field uses); a
            # strict int(row["quantity"]) rejects what validation just
            # accepted, silently dropping the row at confirm time on a row
            # the user was told was valid (mirrors transform_purchase_orders'
            # identical fix for the same class of row).
            try:
                quantity = int(normalize_amount(row["quantity"]))
                unit_price = normalize_amount(row["unit_price"])
                sale_date = normalize_date(row["sale_date"])
            except (KeyError, ValueError, InvalidOperation) as e:
                self.warnings.append(
                    ValidationIssue(
                        entity="sales",
                        row=i,
                        severity="error",
                        message=f"Could not parse row: {e}",
                    )
                )
                continue

            variant_id = None
            if row.get("variant_source_id"):
                variant_id = self.id_map.lookup(
                    "product_variants", row["variant_source_id"]
                )

            customer_id = None
            if row.get("customer_source_id"):
                customer_id = self.id_map.lookup("customers", row["customer_source_id"])

            location_id = None
            source_location = row.get("location_name") or row.get("location_source_id")
            if source_location:
                location_id = location_map.get(source_location)
                if location_id is None:
                    self.warnings.append(
                        ValidationIssue(
                            entity="sales",
                            row=i,
                            field="location_name",
                            severity="warning",
                            message=f"Location {source_location!r} not mapped — assigned to default location",
                        )
                    )

            out.append(
                {
                    "product_id": product_id,
                    "variant_id": variant_id,
                    "customer_id": customer_id,
                    "location_id": location_id,
                    "quantity": quantity,
                    "unit_price": unit_price,
                    "total_amount": unit_price * quantity,
                    "currency": row.get("currency", "NGN").upper(),
                    "sale_date": sale_date,
                    "channel": normalize_channel(row.get("channel")),
                    "payment_method": normalize_payment_method(
                        row.get("payment_method")
                    ),
                    "business_id": self.business_id,
                    "recorded_by": self.created_by,
                }
            )
        return out

    def transform_purchase_orders(self, raw_rows: list[dict]) -> list[dict]:
        """Rows are one-line-item-per-row; rows sharing the same `source_id`
        group into one purchase order with multiple line items (mirrors how
        a business would naturally list "PO-001, ProductA, 10" / "PO-001,
        ProductB, 5" as two rows of the same order).
        """
        groups: dict[str, dict] = {}
        order = []
        for i, row in enumerate(raw_rows, start=2):
            source_id = row.get("source_id") or f"__row_{i}"
            product_id = self.id_map.lookup("products", row.get("product_source_id"))
            if product_id is None:
                self.warnings.append(
                    ValidationIssue(
                        entity="purchase_orders",
                        row=i,
                        field="product_source_id",
                        severity="error",
                        message=f"Product {row.get('product_source_id')!r} could not be resolved",
                    )
                )
                continue

            try:
                # Parsed the same lenient way validate_entity_rows() checks
                # it (comma-thousands, decimal strings) — a plain int(row[...])
                # here would reject values the validator already accepted
                # (e.g. "1,000" or "10.0"), silently dropping the line item
                # at confirm time on a row that passed validation clean.
                quantity = int(normalize_amount(row["quantity"]))
                unit_cost = normalize_amount(row["unit_cost"])
                order_date = (
                    normalize_date(row["order_date"]) if row.get("order_date") else None
                )
                fx_rate = (
                    normalize_amount(row["fx_rate"]) if row.get("fx_rate") else None
                )
            except (KeyError, ValueError, InvalidOperation) as e:
                self.warnings.append(
                    ValidationIssue(
                        entity="purchase_orders",
                        row=i,
                        severity="error",
                        message=f"Could not parse row: {e}",
                    )
                )
                continue

            variant_id = None
            if row.get("variant_source_id"):
                variant_id = self.id_map.lookup(
                    "product_variants", row["variant_source_id"]
                )
                if variant_id is None:
                    # Unlike product_source_id (a hard error that drops the
                    # row above), a stale/typo'd variant reference doesn't
                    # need to be fatal — the line item still has a valid
                    # product to import against. But it must not be
                    # confused with the "recognized, tracked at product
                    # level" case below: this reference was never resolved
                    # at all.
                    self.warnings.append(
                        ValidationIssue(
                            entity="purchase_orders",
                            row=i,
                            field="variant_source_id",
                            severity="warning",
                            message=(
                                f"Variant {row['variant_source_id']!r} could not be "
                                f"resolved — {quantity} units were added to "
                                f"{row.get('product_source_id')!r}'s overall stock "
                                "instead."
                            ),
                        )
                    )
                else:
                    # Purchase-order delivery (transition_status(), reused as-is
                    # from the real-time order flow) applies stock/FIFO-batch
                    # changes at the product level only — it has no variant-aware
                    # path today, imported or not. It also silently replaces
                    # unit_cost with the variant's cost_price_override, if one is
                    # set, before computing the order total and FIFO landed
                    # cost — correct for a real-time PO (use the negotiated
                    # cost), wrong for a historical import (the point is
                    # preserving the actual price paid). Surface both honestly
                    # rather than silently mis-tracking stock or cost.
                    self.warnings.append(
                        ValidationIssue(
                            entity="purchase_orders",
                            row=i,
                            field="variant_source_id",
                            severity="warning",
                            message=(
                                f"{quantity} units will be added to "
                                f"{row.get('product_source_id')!r}'s overall stock, not "
                                "tracked against this specific variant. If this variant "
                                "has a cost override set, its imported unit_cost of "
                                f"{unit_cost} will also be replaced by that override — "
                                "purchase-order delivery doesn't support variant-level "
                                "stock or historical-cost overrides yet."
                            ),
                        )
                    )

            if source_id not in groups:
                groups[source_id] = {
                    "source_id": source_id,
                    "supplier_id": None,
                    "supplier_name": row.get("supplier_name") or source_id,
                    "location_id": None,
                    "currency": None,
                    "order_date": None,
                    "fx_rate": None,
                    "_first_row": i,
                    "line_items": [],
                }
                order.append(groups[source_id])

            # Order-level fields — a business can naturally export them on
            # whichever line-item row happened to carry the value (e.g. only
            # the first row of the PO has order_date filled in), so every
            # row for this source_id gets a chance to fill in whatever the
            # group is still missing, instead of only ever looking at the
            # row that happened to create the group.
            group = groups[source_id]
            if group["supplier_id"] is None and row.get("supplier_source_id"):
                group["supplier_id"] = self.id_map.lookup(
                    "suppliers", row["supplier_source_id"]
                )
            if group["location_id"] is None and row.get("location_source_id"):
                group["location_id"] = self.id_map.lookup(
                    "business_locations", row["location_source_id"]
                )
            if group["currency"] is None and row.get("currency"):
                group["currency"] = row["currency"].upper()
            if group["order_date"] is None and order_date is not None:
                group["order_date"] = order_date
            # Order-level, not per-line-item — the real-time PO flow only
            # ever captures one FX rate per order too. If left unset,
            # transition_status() falls back to a hardcoded 1500 NGN/USD
            # rate, which silently misstates landed cost/COGS for any
            # historical purchase where the real rate differed.
            if group["fx_rate"] is None and fx_rate is not None:
                group["fx_rate"] = fx_rate

            groups[source_id]["line_items"].append(
                {
                    "product_id": product_id,
                    "variant_id": variant_id,
                    "quantity": quantity,
                    "unit_cost": unit_cost,
                }
            )

        result = [g for g in order if g["line_items"]]
        for group in result:
            if group["currency"] is None:
                group["currency"] = "USD"
            if group["order_date"] is None:
                # load_purchase_orders() passes this straight through as the
                # DELIVERED transition's actual_delivery_date;
                # transition_status() falls back to date.today() when it's
                # None, which would backdate every PO missing this column
                # (on every one of its rows) to "today" and skew FIFO
                # batch ordering for a historical import.
                self.warnings.append(
                    ValidationIssue(
                        entity="purchase_orders",
                        row=group["_first_row"],
                        field="order_date",
                        severity="warning",
                        message=(
                            f"No order_date for {group['source_id']!r} — it will be "
                            "recorded as delivered today instead of its real historical "
                            "date, which affects FIFO cost-basis ordering."
                        ),
                    )
                )
            del group["_first_row"]
        return result

    def detect_ghost_products(
        self, sales_raw: list[dict], known_product_source_ids: set[str]
    ) -> list[dict]:
        """Sale rows referencing a product not in the products upload get a
        placeholder ("ghost") product so the sale can still be imported and
        history is preserved.
        """
        seen: set[str] = set()
        ghosts = []
        for row in sales_raw:
            source_id = row.get("product_source_id")
            if (
                not source_id
                or source_id in known_product_source_ids
                or source_id in seen
            ):
                continue
            seen.add(source_id)
            display_name = row.get("product_name") or source_id
            ghosts.append(
                {
                    "source_id": source_id,
                    "name": f"[Deleted Product: {display_name}]",
                    "sku": "",
                    "barcode": "",
                    "unit_cost": "0",
                    "selling_price": "0",
                    "currency": "NGN",
                    "is_active": "false",
                }
            )
            self.warnings.append(
                ValidationIssue(
                    entity="products",
                    row=0,
                    field="product_source_id",
                    severity="warning",
                    message=f"Product {source_id!r} not found in upload — imported as a ghost record",
                )
            )
        return ghosts
