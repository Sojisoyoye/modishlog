"""Shopify CSV adapter — Phase 1 work unit.

Maps Shopify's orders/products CSV export column names to ModishLog field
names. Notably `Option1 Name`/`Option1 Value` (and Option2/Option3) need to
collapse into `product_variants` rows with an `attributes` map.
"""

from src.data_import.etl.adapters.base import BaseCSVAdapter


class ShopifyCSVAdapter(BaseCSVAdapter):
    def map_row(self, entity: str, raw_row: dict[str, str]) -> dict[str, str]:
        raise NotImplementedError(
            "Shopify CSV column mapping — Phase 1 work unit, not yet implemented"
        )
