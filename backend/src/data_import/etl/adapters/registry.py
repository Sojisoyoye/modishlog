"""Static adapter registry — source_system -> adapter class, per extraction mode.

Phase 1 workers each own exactly one file under `etl/adapters/` and never
need to touch this file: every vendor is already imported and wired here as
a `NotImplementedError` stub.
"""

from src.data_import.etl.adapters.base import BaseCSVAdapter
from src.data_import.etl.adapters.generic import GenericCSVAdapter
from src.data_import.etl.adapters.quickbooks import QuickBooksCSVAdapter
from src.data_import.etl.adapters.quickbooks_api import QuickBooksAPIExtractor
from src.data_import.etl.adapters.shopify import ShopifyCSVAdapter
from src.data_import.etl.adapters.shopify_api import ShopifyAPIExtractor
from src.data_import.etl.adapters.ultimatepos import UltimatePOSCSVAdapter
from src.data_import.etl.adapters.ultimatepos_api import UltimatePOSAPIExtractor
from src.data_import.etl.extractor import APIExtractor

CSV_ADAPTERS: dict[str, type[BaseCSVAdapter]] = {
    "generic": GenericCSVAdapter,
    "ultimatepos": UltimatePOSCSVAdapter,
    "shopify": ShopifyCSVAdapter,
    "quickbooks": QuickBooksCSVAdapter,
}

API_ADAPTERS: dict[str, type[APIExtractor]] = {
    "ultimatepos": UltimatePOSAPIExtractor,
    "shopify": ShopifyAPIExtractor,
    "quickbooks": QuickBooksAPIExtractor,
}
