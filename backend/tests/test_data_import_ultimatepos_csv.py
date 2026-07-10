"""Tests for the UltimatePOS CSV adapter (task 162, Phase 1 work unit).

UltimatePOS's live API uses snake_case field names (`variation_id`,
`sell_price_inc_tax`, `tax_amount`, `discount_amount`, ...) — see
`backend/scripts/pos_migrate.py`. Its CSV *export* generally title-cases and
spaces those same names (e.g. "Product Name", "Sub SKU", "Sell Price Inc Tax").
The adapter must tolerate both header styles since exports vary by
UltimatePOS version/report.
"""

from src.data_import.etl.adapters.ultimatepos import UltimatePOSCSVAdapter


class TestProductCategories:
    def test_maps_snake_case_headers(self):
        adapter = UltimatePOSCSVAdapter()
        row = {
            "id": "10",
            "name": "Fabrics",
            "description": "All fabric SKUs",
            "parent_id": "",
        }
        result = adapter.map_row("product_categories", row)
        assert result == {
            "source_id": "10",
            "name": "Fabrics",
            "description": "All fabric SKUs",
            "parent_source_id": "",
        }

    def test_maps_title_case_export_headers(self):
        adapter = UltimatePOSCSVAdapter()
        row = {
            "Category ID": "11",
            "Category Name": "Ankara",
            "Description": "",
            "Parent Category ID": "10",
        }
        result = adapter.map_row("product_categories", row)
        assert result["source_id"] == "11"
        assert result["name"] == "Ankara"
        assert result["parent_source_id"] == "10"


class TestProducts:
    def test_maps_snake_case_api_style_headers(self):
        adapter = UltimatePOSCSVAdapter()
        row = {
            "id": "273939",
            "product": "MDF UV 18mm",
            "sku": "MDF-UV-18",
            "barcode": "1234567890",
            "purchase_price": "8026.0000",
            "selling_price": "10500.0000",
            "category_id": "5",
            "is_inactive": "0",
        }
        result = adapter.map_row("products", row)
        assert result == {
            "source_id": "273939",
            "name": "MDF UV 18mm",
            "sku": "MDF-UV-18",
            "barcode": "1234567890",
            "unit_cost": "8026.0000",
            "selling_price": "10500.0000",
            "currency": "NGN",
            "category_source_id": "5",
            "is_active": "true",
        }

    def test_maps_title_case_export_headers_and_inactive_flag(self):
        adapter = UltimatePOSCSVAdapter()
        row = {
            "Product ID": "9",
            "Product Name": "Ankara Fabric",
            "SKU": "ANK-01",
            "Barcode": "",
            "Purchase Price": "1200.00",
            "Selling Price": "2000.00",
            "Category ID": "3",
            "Is Inactive": "1",
        }
        result = adapter.map_row("products", row)
        assert result["source_id"] == "9"
        assert result["name"] == "Ankara Fabric"
        assert result["unit_cost"] == "1200.00"
        assert result["selling_price"] == "2000.00"
        assert result["is_active"] == "false"

    def test_defaults_currency_to_ngn_when_absent(self):
        adapter = UltimatePOSCSVAdapter()
        row = {"id": "1", "product": "Widget", "sku": "W1"}
        result = adapter.map_row("products", row)
        assert result["currency"] == "NGN"

    def test_category_name_column_is_not_used_as_category_source_id(self):
        """UltimatePOS's product API/export `category` column holds a
        human-readable name (see pos_migrate.py's `p.get("category", "")`),
        not an id — mapping it into category_source_id would silently create
        an unresolvable reference in the transformer's id_map lookup."""
        adapter = UltimatePOSCSVAdapter()
        row = {
            "id": "1",
            "product": "Widget",
            "sku": "W1",
            "category": "MDF Boards",
        }
        result = adapter.map_row("products", row)
        assert result["category_source_id"] == ""

    def test_missing_name_key_raises_keyerror(self):
        """No product-name column at all is a malformed export, not a
        best-effort mapping situation — surface it loudly."""
        adapter = UltimatePOSCSVAdapter()
        row = {"id": "1", "sku": "W1"}
        import pytest

        with pytest.raises(KeyError):
            adapter.map_row("products", row)


class TestProductVariants:
    def test_maps_variation_fields_and_builds_attributes_string(self):
        adapter = UltimatePOSCSVAdapter()
        row = {
            "variation_id": "555",
            "product_id": "273939",
            "name": "Small",
            "sub_sku": "MDF-UV-18-S",
            "sub_barcode": "999",
            "sell_price_inc_tax": "10500.0000",
            "default_purchase_price": "8026.0000",
        }
        result = adapter.map_row("product_variants", row)
        assert result["source_id"] == "555"
        assert result["product_source_id"] == "273939"
        assert result["name"] == "Small"
        assert result["sku"] == "MDF-UV-18-S"
        assert result["barcode"] == "999"
        assert result["price_override"] == "10500.0000"
        assert result["cost_price_override"] == "8026.0000"

    def test_attribute_columns_are_combined_into_attributes_string(self):
        adapter = UltimatePOSCSVAdapter()
        row = {
            "variation_id": "556",
            "product_id": "273939",
            "name": "Blue / Large",
            "variation_value_1_name": "Color",
            "variation_value_1": "Blue",
            "variation_value_2_name": "Size",
            "variation_value_2": "Large",
        }
        result = adapter.map_row("product_variants", row)
        assert result["attributes"] == "Color:Blue;Size:Large"

    def test_missing_product_id_raises_keyerror(self):
        adapter = UltimatePOSCSVAdapter()
        row = {"variation_id": "1", "name": "Small"}
        import pytest

        with pytest.raises(KeyError):
            adapter.map_row("product_variants", row)


class TestSuppliers:
    def test_maps_contact_fields(self):
        adapter = UltimatePOSCSVAdapter()
        row = {
            "id": "42",
            "name": "Acme Textiles",
            "email": "sales@acme.example",
            "mobile": "2348012345678",
        }
        result = adapter.map_row("suppliers", row)
        assert result == {
            "source_id": "42",
            "name": "Acme Textiles",
            "email": "sales@acme.example",
            "contact_person": "",
            "mobile": "2348012345678",
        }

    def test_supplier_business_name_used_as_contact_person_when_present(self):
        adapter = UltimatePOSCSVAdapter()
        row = {
            "id": "43",
            "name": "Jane Doe",
            "supplier_business_name": "Acme Textiles Ltd",
            "email": "",
            "mobile": "",
        }
        result = adapter.map_row("suppliers", row)
        assert result["name"] == "Jane Doe"
        assert result["contact_person"] == "Acme Textiles Ltd"


class TestCustomers:
    def test_maps_contact_fields(self):
        adapter = UltimatePOSCSVAdapter()
        row = {
            "id": "77",
            "name": "Jane Customer",
            "email": "jane@example.com",
            "mobile": "2348000000000",
        }
        result = adapter.map_row("customers", row)
        assert result == {
            "source_id": "77",
            "name": "Jane Customer",
            "email": "jane@example.com",
            "contact_number": "2348000000000",
        }

    def test_contact_no_column_used_when_mobile_absent(self):
        adapter = UltimatePOSCSVAdapter()
        row = {"id": "78", "name": "Bob Customer", "contact_no": "070000000"}
        result = adapter.map_row("customers", row)
        assert result["contact_number"] == "070000000"


class TestBusinessLocations:
    def test_maps_location_fields(self):
        adapter = UltimatePOSCSVAdapter()
        row = {"id": "1", "name": "Lagos HQ", "location_id": "LGA001"}
        result = adapter.map_row("business_locations", row)
        assert result == {
            "source_id": "1",
            "name": "Lagos HQ",
            "location_code": "LGA001",
        }

    def test_location_code_falls_back_to_empty_string(self):
        adapter = UltimatePOSCSVAdapter()
        row = {"id": "2", "name": "Abuja Branch"}
        result = adapter.map_row("business_locations", row)
        assert result["location_code"] == ""


class TestSales:
    def test_maps_sell_line_fields(self):
        adapter = UltimatePOSCSVAdapter()
        row = {
            "product_id": "273939",
            "variation_id": "555",
            "contact_id": "77",
            "quantity": "2",
            "unit_price_inc_tax": "10500.0000",
            "transaction_date": "2026-07-01 10:00:00",
            "payment_type": "cash",
            "location_name": "Lagos HQ",
        }
        result = adapter.map_row("sales", row)
        assert result["product_source_id"] == "273939"
        assert result["variant_source_id"] == "555"
        assert result["customer_source_id"] == "77"
        assert result["quantity"] == "2"
        assert result["unit_price"] == "10500.0000"
        assert result["sale_date"] == "2026-07-01 10:00:00"
        assert result["payment_method"] == "cash"
        assert result["location_name"] == "Lagos HQ"
        assert result["channel"] == "retail"

    def test_defaults_channel_to_retail_when_absent(self):
        adapter = UltimatePOSCSVAdapter()
        row = {
            "product_id": "1",
            "quantity": "1",
            "unit_price_inc_tax": "10.00",
            "transaction_date": "2026-01-01",
        }
        result = adapter.map_row("sales", row)
        assert result["channel"] == "retail"

    def test_pos_channel_mapped_to_retail_and_online_passed_through(self):
        adapter = UltimatePOSCSVAdapter()
        pos_row = {
            "product_id": "1",
            "quantity": "1",
            "unit_price_inc_tax": "10.00",
            "transaction_date": "2026-01-01",
            "sale_type": "pos",
        }
        online_row = {
            "product_id": "1",
            "quantity": "1",
            "unit_price_inc_tax": "10.00",
            "transaction_date": "2026-01-01",
            "sale_type": "online",
        }
        assert adapter.map_row("sales", pos_row)["channel"] == "retail"
        assert adapter.map_row("sales", online_row)["channel"] == "online"

    def test_missing_quantity_raises_keyerror(self):
        adapter = UltimatePOSCSVAdapter()
        row = {"product_id": "1", "unit_price_inc_tax": "10.00", "transaction_date": "2026-01-01"}
        import pytest

        with pytest.raises(KeyError):
            adapter.map_row("sales", row)


class TestUnknownEntity:
    def test_unknown_entity_passes_row_through_unchanged(self):
        adapter = UltimatePOSCSVAdapter()
        row = {"foo": "bar"}
        assert adapter.map_row("not_a_real_entity", row) == row


class TestMapRows:
    def test_map_rows_applies_map_row_to_every_row(self):
        adapter = UltimatePOSCSVAdapter()
        rows = [
            {"id": "1", "name": "Fabrics"},
            {"id": "2", "name": "Ankara", "parent_id": "1"},
        ]
        result = adapter.map_rows("product_categories", rows)
        assert [r["source_id"] for r in result] == ["1", "2"]
        assert result[1]["parent_source_id"] == "1"
