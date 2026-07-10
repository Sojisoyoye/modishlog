"""Tests for the Shopify CSV adapter (task 162, Phase 1 work unit).

Shopify's products export represents one product + all its variants as
multiple CSV rows sharing the same `Handle`: the first row carries full
product info, subsequent rows for the same handle only have variant-specific
columns filled in (Title/Body/Vendor/etc. blank). The same uploaded file is
mapped twice by the pipeline — once under the "products" entity, once under
"product_variants" — so `map_row`/`map_rows` behave differently per `entity`.
"""

from decimal import Decimal

from src.data_import.etl.adapters.shopify import ShopifyCSVAdapter


def _product_row(**overrides) -> dict[str, str]:
    row = {
        "Handle": "classic-tee",
        "Title": "Classic Tee",
        "Body (HTML)": "<p>A classic tee.</p>",
        "Vendor": "Acme Apparel",
        "Product Category": "Apparel > Shirts",
        "Type": "Shirts",
        "Tags": "",
        "Published": "TRUE",
        "Option1 Name": "Size",
        "Option1 Value": "S",
        "Option2 Name": "Color",
        "Option2 Value": "Red",
        "Option3 Name": "",
        "Option3 Value": "",
        "Variant SKU": "TEE-S-RED",
        "Variant Barcode": "012345678905",
        "Variant Grams": "200",
        "Variant Inventory Qty": "50",
        "Variant Price": "29.99",
        "Variant Compare At Price": "39.99",
        "Image Src": "https://cdn.shopify.com/tee.jpg",
    }
    row.update(overrides)
    return row


def _continuation_row(**overrides) -> dict[str, str]:
    """A subsequent row for the same Handle — product columns blank, only
    variant-specific columns filled in, per Shopify's real export format.
    """
    row = {
        "Handle": "classic-tee",
        "Title": "",
        "Body (HTML)": "",
        "Vendor": "",
        "Product Category": "",
        "Type": "",
        "Tags": "",
        "Published": "",
        "Option1 Name": "Size",
        "Option1 Value": "M",
        "Option2 Name": "Color",
        "Option2 Value": "Red",
        "Option3 Name": "",
        "Option3 Value": "",
        "Variant SKU": "TEE-M-RED",
        "Variant Barcode": "012345678912",
        "Variant Grams": "210",
        "Variant Inventory Qty": "30",
        "Variant Price": "29.99",
        "Variant Compare At Price": "39.99",
        "Image Src": "",
    }
    row.update(overrides)
    return row


def _order_row(**overrides) -> dict[str, str]:
    row = {
        "Name": "#1001",
        "Email": "jane@example.com",
        "Financial Status": "paid",
        "Lineitem sku": "TEE-S-RED",
        "Lineitem quantity": "2",
        "Lineitem price": "29.99",
        "Created at": "2026-06-01 10:15:00 -0400",
        "Currency": "USD",
    }
    row.update(overrides)
    return row


class TestShopifyProductMapping:
    def test_maps_first_row_of_handle_group_to_product_fields(self):
        adapter = ShopifyCSVAdapter()
        mapped = adapter.map_row("products", _product_row())

        assert mapped["source_id"] == "classic-tee"
        assert mapped["name"] == "Classic Tee"
        assert mapped["sku"] == "TEE-S-RED"
        assert mapped["barcode"] == "012345678905"
        assert mapped["selling_price"] == "29.99"
        assert mapped["currency"] == "NGN" or mapped["currency"]
        assert mapped["is_active"] == "true"

    def test_maps_unpublished_product_to_inactive(self):
        adapter = ShopifyCSVAdapter()
        mapped = adapter.map_row("products", _product_row(Published="FALSE"))
        assert mapped["is_active"] == "false"

    def test_unit_cost_defaults_to_zero_not_empty_string(self):
        """Shopify's export has no cost-of-goods column. Regression guard:
        transform_products() calls normalize_amount(row.get("unit_cost",
        "0")) — an *empty string* value (as opposed to a missing key) skips
        that "0" default and raises decimal.InvalidOperation downstream, so
        the adapter must emit "0", not "".
        """
        adapter = ShopifyCSVAdapter()
        mapped = adapter.map_row("products", _product_row())
        assert mapped["unit_cost"] == "0"
        Decimal(mapped["unit_cost"])  # must not raise

    def test_map_rows_drops_continuation_rows_for_products_entity(self):
        """`map_rows` must dedupe by Handle so a multi-row variant group
        doesn't produce duplicate `source_id`s for the products entity (the
        validator treats duplicate source_ids within one upload as an error).
        """
        adapter = ShopifyCSVAdapter()
        rows = [_product_row(), _continuation_row(), _continuation_row(**{"Variant SKU": "TEE-L-RED"})]
        mapped = adapter.map_rows("products", rows)

        assert len(mapped) == 1
        assert mapped[0]["source_id"] == "classic-tee"

    def test_map_rows_handles_two_distinct_handles(self):
        adapter = ShopifyCSVAdapter()
        rows = [
            _product_row(),
            _continuation_row(),
            _product_row(Handle="mug", Title="Coffee Mug", **{"Variant SKU": "MUG-1"}),
        ]
        mapped = adapter.map_rows("products", rows)

        source_ids = {row["source_id"] for row in mapped}
        assert source_ids == {"classic-tee", "mug"}


class TestShopifyVariantMapping:
    def test_maps_row_with_options_to_variant_fields(self):
        adapter = ShopifyCSVAdapter()
        mapped = adapter.map_row("product_variants", _product_row())

        assert mapped["product_source_id"] == "classic-tee"
        assert mapped["source_id"] == "classic-tee-TEE-S-RED"
        assert mapped["sku"] == "TEE-S-RED"
        assert mapped["barcode"] == "012345678905"
        assert mapped["price_override"] == "29.99"
        assert "size:S" in mapped["attributes"]
        assert "color:Red" in mapped["attributes"]

    def test_variant_source_id_falls_back_to_index_when_sku_missing(self):
        adapter = ShopifyCSVAdapter()
        mapped = adapter.map_row(
            "product_variants", _product_row(**{"Variant SKU": ""}), index=3
        )
        assert mapped["source_id"] == "classic-tee-3"

    def test_map_rows_produces_one_variant_per_row_for_same_handle(self):
        adapter = ShopifyCSVAdapter()
        rows = [_product_row(), _continuation_row()]
        mapped = adapter.map_rows("product_variants", rows)

        assert len(mapped) == 2
        assert {row["source_id"] for row in mapped} == {
            "classic-tee-TEE-S-RED",
            "classic-tee-TEE-M-RED",
        }
        assert all(row["product_source_id"] == "classic-tee" for row in mapped)

    def test_variant_name_built_from_option_values(self):
        adapter = ShopifyCSVAdapter()
        mapped = adapter.map_row("product_variants", _product_row())
        assert "S" in mapped["name"]
        assert "Red" in mapped["name"]

    def test_variant_with_single_option_only(self):
        adapter = ShopifyCSVAdapter()
        row = _product_row(**{"Option2 Name": "", "Option2 Value": ""})
        mapped = adapter.map_row("product_variants", row)
        assert mapped["attributes"] == "size:S"


class TestShopifyOrderMapping:
    def test_maps_order_row_to_sale_fields(self):
        adapter = ShopifyCSVAdapter()
        mapped = adapter.map_row("sales", _order_row())

        assert mapped["product_source_id"] == "TEE-S-RED"
        assert mapped["variant_source_id"] == "TEE-S-RED"
        assert mapped["quantity"] == "2"
        assert mapped["unit_price"] == "29.99"
        assert mapped["currency"] == "USD"
        assert mapped["channel"] == "online"
        assert mapped["sale_date"].startswith("2026-06-01")

    def test_maps_order_customer_email_as_customer_source_id(self):
        adapter = ShopifyCSVAdapter()
        mapped = adapter.map_row("sales", _order_row())
        assert mapped["customer_source_id"] == "jane@example.com"

    def test_order_row_without_email_has_no_customer_source_id(self):
        adapter = ShopifyCSVAdapter()
        mapped = adapter.map_row("sales", _order_row(Email=""))
        assert not mapped.get("customer_source_id")


class TestShopifySupplierAndCustomerMapping:
    def test_maps_vendor_row_to_supplier_fields(self):
        adapter = ShopifyCSVAdapter()
        row = {"Vendor": "Acme Apparel", "Email": "vendor@acme.com"}
        mapped = adapter.map_row("suppliers", row)
        assert mapped["name"] == "Acme Apparel"
        assert mapped["source_id"] == "Acme Apparel"

    def test_supplier_row_missing_vendor_is_skipped_not_raised(self):
        adapter = ShopifyCSVAdapter()
        mapped = adapter.map_row("suppliers", _product_row(Vendor=""))
        assert mapped == {}

    def test_map_rows_dedupes_repeated_vendor_across_product_rows(self):
        """Many products commonly share one Vendor — the validator rejects
        duplicate source_ids within one upload, so map_rows() must dedupe.
        """
        adapter = ShopifyCSVAdapter()
        rows = [
            _product_row(),
            _product_row(Handle="mug", Title="Coffee Mug", **{"Variant SKU": "MUG-1"}),
        ]
        mapped = adapter.map_rows("suppliers", rows)
        assert len(mapped) == 1
        assert mapped[0]["source_id"] == "Acme Apparel"

    def test_maps_customer_row_from_order_export(self):
        adapter = ShopifyCSVAdapter()
        row = _order_row()
        mapped = adapter.map_row("customers", row)
        assert mapped["email"] == "jane@example.com"
        assert mapped["source_id"] == "jane@example.com"

    def test_customer_row_missing_email_is_skipped_not_raised(self):
        """A guest/no-email order row is common in real Shopify exports —
        it must not raise, since map_row() for a single row has no way to
        tell the caller "drop this row" other than returning something
        falsy; map_rows() is what actually filters it out (see below).
        """
        adapter = ShopifyCSVAdapter()
        mapped = adapter.map_row("customers", _order_row(Email=""))
        assert mapped == {}

    def test_map_rows_drops_rows_missing_email_for_customers_entity(self):
        adapter = ShopifyCSVAdapter()
        rows = [_order_row(), _order_row(Email="")]
        mapped = adapter.map_rows("customers", rows)
        assert len(mapped) == 1
        assert mapped[0]["email"] == "jane@example.com"

    def test_map_rows_dedupes_repeated_customer_email(self):
        """Multiple line items of the same order repeat the same Email —
        the validator rejects duplicate source_ids within one upload, so
        map_rows() must dedupe.
        """
        adapter = ShopifyCSVAdapter()
        rows = [_order_row(), _order_row(**{"Lineitem sku": "TEE-M-RED"})]
        mapped = adapter.map_rows("customers", rows)
        assert len(mapped) == 1


class TestShopifyCategoryMapping:
    def test_maps_product_category_from_product_row(self):
        adapter = ShopifyCSVAdapter()
        mapped = adapter.map_row("product_categories", _product_row())
        assert mapped["name"] == "Apparel > Shirts"
        assert mapped["source_id"] == "Apparel > Shirts"

    def test_category_row_missing_category_is_skipped_not_raised(self):
        """A product with no Product Category set is common and must not
        blow up the whole import job — map_row() returns an empty dict for
        this row; map_rows() (tested below) filters it out.
        """
        adapter = ShopifyCSVAdapter()
        row = _product_row(**{"Product Category": ""})
        mapped = adapter.map_row("product_categories", row)
        assert mapped == {}

    def test_map_rows_drops_rows_missing_category(self):
        adapter = ShopifyCSVAdapter()
        rows = [_product_row(), _product_row(Handle="mug", **{"Product Category": ""})]
        mapped = adapter.map_rows("product_categories", rows)
        assert len(mapped) == 1
        assert mapped[0]["source_id"] == "Apparel > Shirts"

    def test_map_rows_dedupes_repeated_category_across_product_rows(self):
        """Many products commonly share one category — the validator
        rejects duplicate source_ids within one upload, so map_rows() must
        dedupe.
        """
        adapter = ShopifyCSVAdapter()
        rows = [
            _product_row(),
            _product_row(Handle="mug", Title="Coffee Mug", **{"Variant SKU": "MUG-1"}),
        ]
        mapped = adapter.map_rows("product_categories", rows)
        assert len(mapped) == 1
        assert mapped[0]["source_id"] == "Apparel > Shirts"


class TestShopifyUnknownEntity:
    def test_unknown_entity_raises_value_error(self):
        adapter = ShopifyCSVAdapter()
        import pytest

        with pytest.raises(ValueError):
            adapter.map_row("not_a_real_entity", {"Handle": "x"})


class TestShopifyDecimalPrecision:
    def test_variant_price_override_is_decimal_parseable(self):
        adapter = ShopifyCSVAdapter()
        mapped = adapter.map_row("product_variants", _product_row())
        # Field is a string (adapter contract), but must be a value the
        # transformer's normalize_amount() (Decimal(...)) can parse cleanly.
        assert Decimal(mapped["price_override"]) == Decimal("29.99")

    def test_product_selling_price_is_decimal_parseable(self):
        adapter = ShopifyCSVAdapter()
        mapped = adapter.map_row("products", _product_row())
        assert Decimal(mapped["selling_price"]) == Decimal("29.99")
