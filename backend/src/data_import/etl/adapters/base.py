"""Shared interface every CSV vendor adapter implements."""

from abc import ABC, abstractmethod


class BaseCSVAdapter(ABC):
    """Translates a vendor's CSV export column names into ModishLog's field
    names (the ones `etl.transformer.Transformer` expects: `source_id`,
    `name`, `sku`, `product_source_id`, etc.) before rows reach the
    transformer. One instance per import job.
    """

    @abstractmethod
    def map_row(self, entity: str, raw_row: dict[str, str]) -> dict[str, str]:
        raise NotImplementedError

    def map_rows(self, entity: str, rows: list[dict[str, str]]) -> list[dict[str, str]]:
        return [self.map_row(entity, row) for row in rows]
