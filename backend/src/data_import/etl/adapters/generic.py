"""Generic CSV adapter — passthrough. Expects ModishLog column names exactly,
so there's no vendor-specific mapping to do.
"""

from src.data_import.etl.adapters.base import BaseCSVAdapter


class GenericCSVAdapter(BaseCSVAdapter):
    def map_row(self, entity: str, raw_row: dict[str, str]) -> dict[str, str]:
        return raw_row
