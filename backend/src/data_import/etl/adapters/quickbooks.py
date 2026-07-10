"""QuickBooks CSV adapter — Phase 1 work unit.

QuickBooks exports one CSV file per entity, each with its own standard
column headers (these come from QuickBooks Desktop/Online's documented list
and transaction exports):

- Items export       -> ``products``   (Item Name, Description, Type,
  Sales Price, Purchase Cost, Manufacturer's Part Number, Category)
- Vendors export      -> ``suppliers``  (Vendor Name, Company Name,
  Main Phone, Main Email)
- Customers export    -> ``customers``  (Customer Name, Company Name,
  Main Phone, Main Email)
- Invoices export     -> ``sales``      (Customer, Product/Service, Qty,
  Rate, Amount, Invoice Date)

QuickBooks CSV exports don't reliably carry a stable numeric ID column, so
`source_id` is derived from each entity's natural key instead — QuickBooks
itself treats these names as the unique identity for matching/duplicate
detection (e.g. Item Name must be unique per item, Customer Name/Vendor Name
are the primary keys QuickBooks uses internally), so re-using them as
`source_id` here is safe and stable across repeated imports of the same
export.

QuickBooks has no native multi-attribute product/variant concept, so
``product_variants`` is intentionally unsupported by this adapter.

QuickBooks' Items export has no separate "Categories" file — the ``Category``
column on each Item row is free text. This adapter passes that text through
as ``category_source_id`` unchanged, so it resolves correctly *only* if the
import also includes a ``product_categories`` upload whose rows use the same
text as their ``source_id`` (e.g. a category row with ``source_id=Widgets``
for an Item with ``Category=Widgets``). Without a matching categories upload,
the reference simply doesn't resolve and the product is imported with no
category — never a hard failure.
"""

from datetime import datetime

from src.data_import.etl.adapters.base import BaseCSVAdapter

# QuickBooks (a US-market product) always exports dates in US MM/DD/YYYY
# order. The shared transformer.parse_flexible_date tries %d/%m/%Y (day
# first) before %m/%d/%Y, so passing a QuickBooks date straight through would
# silently swap day/month for any date where the day is <= 12 (e.g.
# "07/10/2026" meaning July 10 would be misread as 10 July -> 7 October).
# Normalising to ISO 8601 here removes the ambiguity before it ever reaches
# the transformer.
_QUICKBOOKS_DATE_FORMAT = "%m/%d/%Y"


def _field(raw_row: dict[str, str], key: str, default: str = "") -> str:
    """Look up a QuickBooks column, tolerating missing keys and blank/
    whitespace-only cells, and fall back to `default` in both cases.
    """
    return (raw_row.get(key) or default).strip() or default


def _normalize_quickbooks_date(raw: str) -> str:
    raw = raw.strip()
    if not raw:
        return ""
    try:
        return datetime.strptime(raw, _QUICKBOOKS_DATE_FORMAT).date().isoformat()
    except ValueError:
        # Not the expected US format (e.g. already ISO, or a locale variant)
        # — pass through unchanged and let the transformer's own flexible
        # date parser attempt it / raise a validation error.
        return raw


def _normalize_quickbooks_qty(raw: str) -> str:
    """QuickBooks allows fractional Qty (weight- or hour-billed items), but
    the transformer does a hard `int()` cast on `quantity` and drops the
    whole sale row if that raises. Round to the nearest whole unit here
    instead of letting a fractional value silently fail downstream.
    """
    raw = raw.strip() or "1"
    try:
        return str(int(raw))
    except ValueError:
        try:
            return str(round(float(raw)) or 1)  # financial-float-ok — quantity, not money
        except ValueError:
            return "1"


class QuickBooksCSVAdapter(BaseCSVAdapter):
    def map_row(self, entity: str, raw_row: dict[str, str]) -> dict[str, str]:
        if entity == "products":
            return self._map_item(raw_row)
        if entity == "suppliers":
            return self._map_vendor(raw_row)
        if entity == "customers":
            return self._map_customer(raw_row)
        if entity == "sales":
            return self._map_invoice(raw_row)
        raise ValueError(
            f"QuickBooks CSV adapter does not support entity {entity!r} "
            "(QuickBooks has no native export for it, e.g. product_variants)"
        )

    # ------------------------------------------------------------------
    # Items export -> products
    # ------------------------------------------------------------------

    def _map_item(self, raw_row: dict[str, str]) -> dict[str, str]:
        name = _field(raw_row, "Item Name")
        if not name:
            raise ValueError("QuickBooks Items row is missing 'Item Name'")

        return {
            # Item Name is QuickBooks' natural key for items — used here as a
            # stable source_id since the export has no numeric ID column.
            "source_id": name,
            "name": name,
            "sku": _field(raw_row, "Manufacturer's Part Number"),
            "barcode": "",
            "unit_cost": _field(raw_row, "Purchase Cost", "0"),
            "selling_price": _field(raw_row, "Sales Price", "0"),
            "currency": "NGN",
            "category_source_id": _field(raw_row, "Category"),
            "is_active": "true",
        }

    # ------------------------------------------------------------------
    # Vendors export -> suppliers
    # ------------------------------------------------------------------

    def _map_vendor(self, raw_row: dict[str, str]) -> dict[str, str]:
        vendor_name = _field(raw_row, "Vendor Name")
        if not vendor_name:
            raise ValueError("QuickBooks Vendors row is missing 'Vendor Name'")

        company_name = _field(raw_row, "Company Name")

        return {
            # Vendor Name is QuickBooks' natural key for vendors.
            "source_id": vendor_name,
            "name": company_name or vendor_name,
            "email": _field(raw_row, "Main Email"),
            "contact_person": vendor_name,
            "mobile": _field(raw_row, "Main Phone"),
        }

    # ------------------------------------------------------------------
    # Customers export -> customers
    # ------------------------------------------------------------------

    def _map_customer(self, raw_row: dict[str, str]) -> dict[str, str]:
        customer_name = _field(raw_row, "Customer Name")
        if not customer_name:
            raise ValueError("QuickBooks Customers row is missing 'Customer Name'")

        company_name = _field(raw_row, "Company Name")

        return {
            # Customer Name is QuickBooks' natural key for customers.
            "source_id": customer_name,
            "name": company_name or customer_name,
            "email": _field(raw_row, "Main Email"),
            "contact_number": _field(raw_row, "Main Phone"),
        }

    # ------------------------------------------------------------------
    # Invoices export -> sales
    # ------------------------------------------------------------------

    def _map_invoice(self, raw_row: dict[str, str]) -> dict[str, str]:
        product_service = _field(raw_row, "Product/Service")
        if not product_service:
            raise ValueError("QuickBooks Invoices row is missing 'Product/Service'")

        return {
            # Product/Service and Customer are QuickBooks' natural keys and
            # must match the source_id derived in _map_item/_map_customer.
            # Customer is intentionally allowed to be blank — QuickBooks
            # invoices for cash/walk-in sales can omit it, which should
            # import as a sale with no linked customer, not a hard error.
            "product_source_id": product_service,
            "variant_source_id": "",
            "customer_source_id": _field(raw_row, "Customer"),
            "quantity": _normalize_quickbooks_qty(raw_row.get("Qty") or ""),
            "unit_price": _field(raw_row, "Rate", "0"),
            "sale_date": _normalize_quickbooks_date(raw_row.get("Invoice Date") or ""),
            "currency": "NGN",
            # QuickBooks Invoices represent invoiced/billed transactions,
            # which map most closely to wholesale-style sales rather than
            # retail POS or online storefront transactions.
            "channel": "wholesale",
            "payment_method": "",
            "location_name": "",
        }
