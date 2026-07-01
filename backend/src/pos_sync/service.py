"""Incremental POS sync service.

Pulls new sells and purchases from the live UltimatePOS system and upserts
them into ModishLog, advancing a watermark after each successful batch so
subsequent runs only fetch records newer than the last-seen POS ID.

Design notes
------------
- Watermarks are stored in the ``pos_sync_state`` table (key-value).
- Deduplication is done via the ``pos_id`` column on Sale / PurchaseOrder:
  if a record with that pos_id already exists we skip it.
- Product matching uses name-based lookup (the same approach as pos_migrate).
- The POSClient makes synchronous HTTP calls; they're run in a thread pool
  via ``asyncio.to_thread`` to keep the event loop unblocked.
- On any unhandled exception the watermark is NOT advanced, so the next
  run will retry the same window.
"""

from __future__ import annotations

import asyncio
import uuid
from dataclasses import dataclass
from datetime import date, datetime, timezone
from decimal import Decimal
from typing import Any

import structlog
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.auth.models import User
from src.orders.models import OrderPaymentStatus, OrderStatus, PurchaseOrder
from src.pos_sync.models import SyncState
from src.products.models import Product
from src.sales.models import Sale, SaleChannel, SaleStatus

logger = structlog.get_logger()

_SELLS_WATERMARK_KEY = "sells_max_id"
_PURCHASES_WATERMARK_KEY = "purchases_max_id"


@dataclass
class SyncResult:
    inserted: int = 0
    skipped: int = 0
    new_watermark: int = 0


class POSSyncService:
    """Stateful per-request sync service wrapping a DB session and POS client."""

    def __init__(self, db: AsyncSession, pos_client: Any) -> None:
        self._db = db
        self._pos_client = pos_client
        # In-memory watermark cache — pre-populated by tests or loaded from DB
        self._watermark_cache: dict[str, int] = {}

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    async def run_incremental_sync(self) -> dict[str, SyncResult]:
        """Run sell and purchase incremental syncs, return combined results."""
        sells_result = await self.sync_sells()
        purchases_result = await self.sync_purchases()
        return {"sells": sells_result, "purchases": purchases_result}

    async def sync_sells(self) -> SyncResult:
        """Fetch new sells from POS and upsert into the sales table."""
        watermark = await self._get_watermark(_SELLS_WATERMARK_KEY)
        all_sells: list[dict] = await asyncio.to_thread(self._pos_client.fetch_sells)

        new_sells = [s for s in all_sells if self._pos_int_id(s) > watermark]

        result = SyncResult(new_watermark=watermark)

        # Hoist expensive lookups once per batch, not once per sell
        name_map = await self._build_product_name_map()
        system_user_id = await self._get_system_user_id()

        for sell in new_sells:
            pos_id = str(self._pos_int_id(sell))
            if await self._sale_pos_id_exists(pos_id):
                result.skipped += 1
                result.new_watermark = max(result.new_watermark, int(pos_id))
                continue
            try:
                rows_inserted = await self._insert_sell(
                    sell, pos_id, name_map=name_map, system_user_id=system_user_id
                )
                result.inserted += rows_inserted
                result.new_watermark = max(result.new_watermark, int(pos_id))
            except Exception as exc:
                await logger.awarning(
                    "pos_sell_insert_failed", pos_id=pos_id, error=str(exc)
                )
                raise

        if result.new_watermark != watermark:
            await self._save_watermark(_SELLS_WATERMARK_KEY, result.new_watermark)
        await logger.ainfo(
            "pos_sells_synced",
            inserted=result.inserted,
            skipped=result.skipped,
            watermark=result.new_watermark,
        )
        return result

    async def sync_purchases(self) -> SyncResult:
        """Fetch new purchases from POS and upsert into the purchase_orders table."""
        watermark = await self._get_watermark(_PURCHASES_WATERMARK_KEY)
        all_purchases: list[dict] = await asyncio.to_thread(
            self._pos_client.fetch_purchases
        )

        new_purchases = [p for p in all_purchases if self._pos_int_id(p) > watermark]

        result = SyncResult(new_watermark=watermark)

        # Hoist expensive lookup once per batch, not once per purchase
        system_user_id = await self._get_system_user_id()

        for purchase in new_purchases:
            pos_id = str(self._pos_int_id(purchase))
            if await self._purchase_pos_id_exists(pos_id):
                result.skipped += 1
                result.new_watermark = max(result.new_watermark, int(pos_id))
                continue
            try:
                await self._insert_purchase(purchase, pos_id, system_user_id=system_user_id)
                result.inserted += 1
                result.new_watermark = max(result.new_watermark, int(pos_id))
            except Exception as exc:
                await logger.awarning(
                    "pos_purchase_insert_failed", pos_id=pos_id, error=str(exc)
                )
                raise

        if result.new_watermark != watermark:
            await self._save_watermark(_PURCHASES_WATERMARK_KEY, result.new_watermark)
        await logger.ainfo(
            "pos_purchases_synced",
            inserted=result.inserted,
            skipped=result.skipped,
            watermark=result.new_watermark,
        )
        return result

    # ------------------------------------------------------------------
    # Watermark helpers
    # ------------------------------------------------------------------

    async def _get_watermark(self, key: str) -> int:
        if key in self._watermark_cache:
            return self._watermark_cache[key]
        result = await self._db.execute(select(SyncState).where(SyncState.key == key))
        row = result.scalar_one_or_none()
        val = int(row.value) if row else 0
        self._watermark_cache[key] = val
        return val

    async def _save_watermark(self, key: str, value: int) -> None:
        result = await self._db.execute(select(SyncState).where(SyncState.key == key))
        row = result.scalar_one_or_none()
        if row:
            row.value = str(value)
            row.updated_at = datetime.now(timezone.utc)
        else:
            self._db.add(SyncState(key=key, value=str(value)))
        await self._db.flush()
        self._watermark_cache[key] = value

    # ------------------------------------------------------------------
    # Existence checks
    # ------------------------------------------------------------------

    async def _sale_pos_id_exists(self, pos_id: str) -> bool:
        result = await self._db.execute(
            select(Sale.id).where(Sale.pos_id == pos_id).limit(1)
        )
        return result.scalar_one_or_none() is not None

    async def _purchase_pos_id_exists(self, pos_id: str) -> bool:
        result = await self._db.execute(
            select(PurchaseOrder.id).where(PurchaseOrder.pos_id == pos_id).limit(1)
        )
        return result.scalar_one_or_none() is not None

    # ------------------------------------------------------------------
    # Insert helpers
    # ------------------------------------------------------------------

    async def _insert_sell(
        self,
        sell: dict,
        pos_id: str,
        *,
        name_map: dict[str, uuid.UUID],
        system_user_id: uuid.UUID,
    ) -> int:
        """Insert one POS sell as one Sale record per line item.

        Returns the number of Sale rows actually inserted (0 if no lines
        matched a known product).
        """
        sell_date = self._parse_date(sell.get("transaction_date") or "")
        lines: list[dict] = sell.get("sell_lines") or []
        rows = 0

        for line in lines:
            product_name: str = ""
            product_info = line.get("product") or {}
            if isinstance(product_info, dict):
                product_name = (product_info.get("name") or "").lower().strip()
            product_id = name_map.get(product_name)
            if not product_id:
                await logger.awarning(
                    "pos_sell_product_not_found",
                    pos_sell_id=pos_id,
                    product_name=product_name,
                )
                continue

            qty_raw = line.get("quantity") or 0
            qty = max(1, int(float(str(qty_raw))))
            unit_price = Decimal(str(line.get("unit_price") or "0"))
            total = Decimal(str(line.get("line_total") or "0"))

            sale = Sale(
                id=uuid.uuid4(),
                product_id=product_id,
                quantity=qty,
                unit_price=unit_price,
                total_amount=total,
                sale_date=sell_date or date.today(),
                channel=SaleChannel.RETAIL,
                status=SaleStatus.COMPLETED,
                recorded_by=system_user_id,
                pos_id=pos_id,
                invoice_number=sell.get("invoice_no"),
                payment_status=sell.get("payment_status"),
            )
            self._db.add(sale)
            rows += 1

        await self._db.flush()
        return rows

    async def _insert_purchase(
        self, purchase: dict, pos_id: str, *, system_user_id: uuid.UUID
    ) -> None:
        """Insert one POS purchase as a PurchaseOrder record."""
        order_date = self._parse_date(purchase.get("transaction_date") or "")
        total = Decimal(str(purchase.get("final_total") or "0"))
        contact = purchase.get("contact") or {}
        supplier_name = (
            (contact.get("name") or "Unknown")
            if isinstance(contact, dict)
            else "Unknown"
        )
        ref_no: str = purchase.get("ref_no") or f"POS-{pos_id}"

        po = PurchaseOrder(
            id=uuid.uuid4(),
            order_number=ref_no,
            supplier_name=supplier_name,
            total_amount=total,
            currency="NGN",
            status=OrderStatus.DELIVERED,
            payment_status=OrderPaymentStatus.PAID,
            order_date=order_date or date.today(),
            created_by=system_user_id,
            pos_id=pos_id,
        )
        self._db.add(po)
        await self._db.flush()

    # ------------------------------------------------------------------
    # Utility
    # ------------------------------------------------------------------

    @staticmethod
    def _pos_int_id(item: dict) -> int:
        """Extract the integer POS ID from a DataTables response row."""
        try:
            return int(item.get("id") or 0)
        except (TypeError, ValueError):
            return 0

    @staticmethod
    def _parse_date(raw: str) -> date | None:
        for fmt in ("%Y-%m-%d", "%d/%m/%Y", "%d-%m-%Y"):
            try:
                return datetime.strptime(raw[:10], fmt).date()
            except (ValueError, IndexError):
                continue
        return None

    async def _build_product_name_map(self) -> dict[str, uuid.UUID]:
        result = await self._db.execute(select(Product.id, Product.name))
        return {name.lower().strip(): pid for pid, name in result.all()}

    async def _get_system_user_id(self) -> uuid.UUID:
        result = await self._db.execute(select(User.id).limit(1))
        row = result.scalar_one_or_none()
        return row if row else uuid.uuid4()
