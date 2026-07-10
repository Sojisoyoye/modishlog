"""Shopify Admin REST API extractor — Phase 1 work unit.

Authenticates with an API key + secret and pulls orders/products/customers
live. Credentials must never be persisted or logged — see
`etl/extractor.APIExtractor`'s docstring.
"""

from src.data_import.etl.extractor import APIExtractor, ExtractedData


class ShopifyAPIExtractor(APIExtractor):
    async def extract(self) -> ExtractedData:
        raise NotImplementedError(
            "Shopify API extraction — Phase 1 work unit, not yet implemented"
        )

    async def test_connection(self) -> dict:
        raise NotImplementedError(
            "Shopify API test-connection — Phase 1 work unit, not yet implemented"
        )
