"""Tests for incremental POS sync service."""

from __future__ import annotations

import uuid
from datetime import date, datetime, timezone
from decimal import Decimal
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

# ---------------------------------------------------------------------------
# Helpers / fixtures
# ---------------------------------------------------------------------------


def _make_pos_sell(
    pos_id: int,
    product_pos_id: str = "1001",
    quantity: float = 1.0,
    unit_price: str = "5000.0",
    total: str = "5000.0",
    date_str: str = "2026-07-01",
) -> dict[str, Any]:
    """Minimal POS sell dict matching UltimatePOS /sells response shape."""
    return {
        "id": pos_id,
        "transaction_date": date_str,
        "final_total": total,
        "sell_lines": [
            {
                "product_id": product_pos_id,
                "quantity": quantity,
                "unit_price": unit_price,
                "line_total": total,
                "product": {"name": "Test Product"},
            }
        ],
        "contact": None,
        "payment_status": "paid",
        "invoice_no": f"INV-{pos_id}",
    }


def _make_pos_purchase(
    pos_id: int,
    date_str: str = "2026-07-01",
    total: str = "10000.0",
) -> dict[str, Any]:
    """Minimal POS purchase dict matching UltimatePOS /purchases response shape."""
    return {
        "id": pos_id,
        "transaction_date": date_str,
        "final_total": total,
        "ref_no": f"PO-{pos_id}",
        "contact": {"name": "Test Supplier"},
        "purchase_lines": [],
        "payment_status": "paid",
    }


# ---------------------------------------------------------------------------
# SyncState model tests
# ---------------------------------------------------------------------------


class TestSyncState:
    def test_import(self):
        """SyncState can be imported from pos_sync.models."""
        from src.pos_sync.models import SyncState  # noqa: F401

    def test_tablename(self):
        from src.pos_sync.models import SyncState
        assert SyncState.__tablename__ == "pos_sync_state"

    def test_has_key_and_value_columns(self):
        from src.pos_sync.models import SyncState
        cols = {c.key for c in SyncState.__table__.columns}
        assert "key" in cols
        assert "value" in cols
        assert "updated_at" in cols


# ---------------------------------------------------------------------------
# POSSyncService — upsert logic
# ---------------------------------------------------------------------------


class TestPOSSyncServiceSells:
    """Test incremental sell sync via mocked DB and POS client."""

    def _make_service(self, sells: list[dict], watermark_value: int = 0):
        """Return a POSSyncService with mocked DB session and POS client."""
        from src.pos_sync.service import POSSyncService

        db = AsyncMock()
        pos_client = MagicMock()
        pos_client.fetch_sells.return_value = sells

        service = POSSyncService(db=db, pos_client=pos_client)
        # Pre-seed the watermark via a side-effect on the DB query
        service._watermark_cache = {"sells_max_id": watermark_value}
        return service, db, pos_client

    @pytest.mark.asyncio
    async def test_new_sells_are_counted(self):
        """sync_sells() returns the count of newly upserted sell records."""
        from src.pos_sync.service import POSSyncService, SyncResult

        sells = [_make_pos_sell(101), _make_pos_sell(102)]
        service, db, pos_client = self._make_service(sells, watermark_value=100)

        # Simulate no existing records for those pos_ids
        service._sale_pos_id_exists = AsyncMock(return_value=False)
        service._insert_sell = AsyncMock()
        service._save_watermark = AsyncMock()

        result = await service.sync_sells()

        assert isinstance(result, SyncResult)
        assert result.inserted == 2
        assert result.skipped == 0
        assert result.new_watermark == 102

    @pytest.mark.asyncio
    async def test_sells_below_watermark_are_skipped(self):
        """Sells with pos_id <= current watermark are not processed."""
        from src.pos_sync.service import POSSyncService

        # POS returns sell 50 and 100, watermark is 100
        sells = [_make_pos_sell(50), _make_pos_sell(100)]
        service, db, pos_client = self._make_service(sells, watermark_value=100)

        service._sale_pos_id_exists = AsyncMock(return_value=False)
        service._insert_sell = AsyncMock()
        service._save_watermark = AsyncMock()

        result = await service.sync_sells()

        # Both are <= watermark so neither should be inserted
        assert result.inserted == 0
        assert service._insert_sell.call_count == 0

    @pytest.mark.asyncio
    async def test_idempotency_duplicate_pos_id_skipped(self):
        """If pos_id already exists in DB, the sell is skipped (not duplicated)."""
        from src.pos_sync.service import POSSyncService

        sells = [_make_pos_sell(101)]
        service, db, pos_client = self._make_service(sells, watermark_value=100)

        # Simulate record already in DB
        service._sale_pos_id_exists = AsyncMock(return_value=True)
        service._insert_sell = AsyncMock()
        service._save_watermark = AsyncMock()

        result = await service.sync_sells()

        assert result.inserted == 0
        assert result.skipped == 1
        service._insert_sell.assert_not_called()

    @pytest.mark.asyncio
    async def test_watermark_advances_to_max_processed_id(self):
        """Watermark advances to the highest pos_id seen in the batch."""
        from src.pos_sync.service import POSSyncService

        sells = [_make_pos_sell(101), _make_pos_sell(105), _make_pos_sell(103)]
        service, db, pos_client = self._make_service(sells, watermark_value=100)

        service._sale_pos_id_exists = AsyncMock(return_value=False)
        service._insert_sell = AsyncMock()
        service._save_watermark = AsyncMock()

        result = await service.sync_sells()

        assert result.new_watermark == 105

    @pytest.mark.asyncio
    async def test_watermark_does_not_advance_on_exception(self):
        """If an insert raises, _save_watermark is NOT called."""
        from src.pos_sync.service import POSSyncService

        sells = [_make_pos_sell(101)]
        service, db, pos_client = self._make_service(sells, watermark_value=100)

        service._sale_pos_id_exists = AsyncMock(return_value=False)
        service._insert_sell = AsyncMock(side_effect=RuntimeError("DB error"))
        service._save_watermark = AsyncMock()

        with pytest.raises(RuntimeError):
            await service.sync_sells()

        service._save_watermark.assert_not_called()

    @pytest.mark.asyncio
    async def test_empty_pos_response_is_noop(self):
        """No sells from POS → result is 0 inserted, watermark unchanged."""
        from src.pos_sync.service import POSSyncService

        service, db, pos_client = self._make_service([], watermark_value=100)
        service._sale_pos_id_exists = AsyncMock(return_value=False)
        service._insert_sell = AsyncMock()
        service._save_watermark = AsyncMock()

        result = await service.sync_sells()

        assert result.inserted == 0
        assert result.new_watermark == 100
        service._insert_sell.assert_not_called()


class TestPOSSyncServicePurchases:
    """Test incremental purchase sync."""

    def _make_service(self, purchases: list[dict], watermark_value: int = 0):
        from src.pos_sync.service import POSSyncService

        db = AsyncMock()
        pos_client = MagicMock()
        pos_client.fetch_purchases.return_value = purchases

        service = POSSyncService(db=db, pos_client=pos_client)
        service._watermark_cache = {"purchases_max_id": watermark_value}
        return service, db, pos_client

    @pytest.mark.asyncio
    async def test_new_purchases_are_counted(self):
        from src.pos_sync.service import POSSyncService, SyncResult

        purchases = [_make_pos_purchase(201), _make_pos_purchase(202)]
        service, db, pos_client = self._make_service(purchases, watermark_value=200)

        service._purchase_pos_id_exists = AsyncMock(return_value=False)
        service._insert_purchase = AsyncMock()
        service._save_watermark = AsyncMock()

        result = await service.sync_purchases()

        assert isinstance(result, SyncResult)
        assert result.inserted == 2
        assert result.new_watermark == 202

    @pytest.mark.asyncio
    async def test_duplicate_purchase_pos_id_skipped(self):
        from src.pos_sync.service import POSSyncService

        purchases = [_make_pos_purchase(201)]
        service, db, pos_client = self._make_service(purchases, watermark_value=200)

        service._purchase_pos_id_exists = AsyncMock(return_value=True)
        service._insert_purchase = AsyncMock()
        service._save_watermark = AsyncMock()

        result = await service.sync_purchases()

        assert result.inserted == 0
        assert result.skipped == 1


# ---------------------------------------------------------------------------
# run_incremental_sync integration
# ---------------------------------------------------------------------------


class TestRunIncrementalSync:
    @pytest.mark.asyncio
    async def test_run_incremental_sync_calls_both_methods(self):
        """run_incremental_sync() calls sync_sells() and sync_purchases()."""
        from src.pos_sync.service import POSSyncService, SyncResult

        db = AsyncMock()
        pos_client = MagicMock()
        pos_client.fetch_sells.return_value = []
        pos_client.fetch_purchases.return_value = []

        service = POSSyncService(db=db, pos_client=pos_client)
        service._watermark_cache = {"sells_max_id": 0, "purchases_max_id": 0}
        service._sale_pos_id_exists = AsyncMock(return_value=False)
        service._purchase_pos_id_exists = AsyncMock(return_value=False)
        service._insert_sell = AsyncMock()
        service._insert_purchase = AsyncMock()
        service._save_watermark = AsyncMock()

        result = await service.run_incremental_sync()

        assert "sells" in result
        assert "purchases" in result
        assert isinstance(result["sells"], SyncResult)
        assert isinstance(result["purchases"], SyncResult)
