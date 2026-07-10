"""UltimatePOS CSV adapter — Phase 1 work unit.

Maps UltimatePOS's CSV export column names (`variation_id`, `sell_price_inc_tax`,
`tax_amount`, `discount_amount`, ...) to ModishLog field names. See
`backend/scripts/pos_migrate.py` for the field names UltimatePOS uses in its
live API — the CSV export uses the same underlying columns.
"""

from src.data_import.etl.adapters.base import BaseCSVAdapter


class UltimatePOSCSVAdapter(BaseCSVAdapter):
    def map_row(self, entity: str, raw_row: dict[str, str]) -> dict[str, str]:
        raise NotImplementedError(
            "UltimatePOS CSV column mapping — Phase 1 work unit, not yet implemented"
        )
