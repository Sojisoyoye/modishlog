"""QuickBooks CSV adapter — Phase 1 work unit.

Maps QuickBooks' export format (Items, Invoices, Bills, Vendors) to
ModishLog field names.
"""

from src.data_import.etl.adapters.base import BaseCSVAdapter


class QuickBooksCSVAdapter(BaseCSVAdapter):
    def map_row(self, entity: str, raw_row: dict[str, str]) -> dict[str, str]:
        raise NotImplementedError(
            "QuickBooks CSV column mapping — Phase 1 work unit, not yet implemented"
        )
