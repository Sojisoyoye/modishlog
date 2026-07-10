"""QuickBooks Online API extractor — Phase 1 work unit.

OAuth 2.0 flow — the access token is passed in from the frontend after the
OAuth redirect completes; this extractor never handles the OAuth handshake
itself. Credentials/tokens must never be persisted or logged — see
`etl/extractor.APIExtractor`'s docstring.
"""

from src.data_import.etl.extractor import APIExtractor, ExtractedData


class QuickBooksAPIExtractor(APIExtractor):
    async def extract(self) -> ExtractedData:
        raise NotImplementedError(
            "QuickBooks API extraction — Phase 1 work unit, not yet implemented"
        )

    async def test_connection(self) -> dict:
        raise NotImplementedError(
            "QuickBooks API test-connection — Phase 1 work unit, not yet implemented"
        )
