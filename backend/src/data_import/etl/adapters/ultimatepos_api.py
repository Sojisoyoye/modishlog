"""UltimatePOS live API extractor — Phase 1 work unit.

Port the `POSClient` auth + entity-pull logic from `backend/scripts/pos_migrate.py`
(cookie/CSRF auth, product/sell/purchase/contact pulls, HTML receipt parsing)
into the `APIExtractor` interface. Credentials must never be persisted or
logged — see `etl/extractor.APIExtractor`'s docstring.
"""

from src.data_import.etl.extractor import APIExtractor, ExtractedData


class UltimatePOSAPIExtractor(APIExtractor):
    async def extract(self) -> ExtractedData:
        raise NotImplementedError(
            "UltimatePOS API extraction — Phase 1 work unit, not yet implemented"
        )

    async def test_connection(self) -> dict:
        raise NotImplementedError(
            "UltimatePOS API test-connection — Phase 1 work unit, not yet implemented"
        )
