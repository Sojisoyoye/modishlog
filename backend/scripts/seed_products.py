"""Seed script: clears all product/sales/order/inventory data and inserts fresh catalog."""

import asyncio
import uuid
from datetime import date, datetime, timezone
from decimal import Decimal

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import sessionmaker

import os, sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

DATABASE_URL = os.environ["DATABASE_URL"]

# ── Category seeds ───────────────────────────────────────────────────────────

CATEGORIES = [
    {"name": "MDF Boards", "description": "Medium-density fiberboard and specialty board types for furniture, cabinetry, and interior panelling. Available in various finishes."},
    {"name": "HDF Boards", "description": "High-density fiberboard with superior strength and ultra-smooth surface. Ideal for door skins, flooring, and premium furniture."},
    {"name": "UV Gloss Boards", "description": "High-gloss UV-coated boards available on MDF and HDF substrates. Perfect for kitchens, wardrobes, and feature walls in Lagos."},
    {"name": "Marine Boards", "description": "Moisture-resistant boards engineered for wet areas including bathrooms, kitchens, and outdoor furniture applications."},
    {"name": "Edge Tapes", "description": "Professional edge banding tapes in 21mm and 48mm widths. Available in matt and gloss finishes to match all board colours."},
    {"name": "Doors", "description": "Interior and exterior doors in flush and panel designs. Available in multiple finishes and standard Nigerian sizes."},
    {"name": "PU Stone Panels", "description": "Lightweight polyurethane stone-effect wall panels for stunning interior and exterior feature walls."},
    {"name": "Block Boards", "description": "Solid block boards with timber core and veneer facing. Strong, stable, and ideal for heavy-duty furniture and structural panelling."},
    {"name": "Accessories", "description": "Fitting accessories, hardware and complementary products for board installation and finishing."},
]

# ── Product seeds ────────────────────────────────────────────────────────────

PRODUCTS = [
    # UV GLOSS BOARDS (MDF base)
    {"name": "Black MDF UV Board", "price": 26500, "stock": 159, "category": "UV Gloss Boards", "sku": "301410"},
    {"name": "Cappuccino MDF UV Board", "price": 26500, "stock": 6, "category": "UV Gloss Boards", "sku": "301415"},
    {"name": "Dark Grey MDF UV Board", "price": 26500, "stock": 244, "category": "UV Gloss Boards", "sku": "301413"},
    {"name": "Light Grey MDF UV Board", "price": 26500, "stock": 79, "category": "UV Gloss Boards", "sku": "301418"},
    {"name": "Off White MDF UV Board", "price": 26500, "stock": 224, "category": "UV Gloss Boards", "sku": "301406"},
    {"name": "Perfect White MDF UV Board", "price": 26500, "stock": 307, "category": "UV Gloss Boards", "sku": "301409"},
    # UV GLOSS BOARDS (HDF base)
    {"name": "Cappuccino HDF UV Board", "price": 44500, "stock": 8, "category": "UV Gloss Boards", "sku": "301425"},
    {"name": "Dark Grey HDF UV Board", "price": 44500, "stock": 1, "category": "UV Gloss Boards", "sku": "301422"},
    {"name": "Off White HDF UV Board", "price": 44500, "stock": 155, "category": "UV Gloss Boards", "sku": "301419"},
    {"name": "Perfect White HDF UV Board", "price": 44500, "stock": 0, "category": "UV Gloss Boards", "sku": "301420"},
    # BLOCK BOARDS
    {"name": "Brown Masonia BB Board", "price": 26000, "stock": 36, "category": "Block Boards", "sku": "333361"},
    {"name": "Customer Code BB Board", "price": 26000, "stock": 0, "category": "Block Boards", "sku": "333360"},
    # EDGE TAPES
    {"name": "Akala Edge Tape 0.5x48MM", "price": 16000, "stock": 0, "category": "Edge Tapes", "sku": "279606"},
    {"name": "Akala Edge Tape 0.5x48MM Gloss", "price": 16500, "stock": 7, "category": "Edge Tapes", "sku": "274841"},
    {"name": "Akala Edge Tape 48MM", "price": 16500, "stock": 30, "category": "Edge Tapes", "sku": "274851"},
    {"name": "Asunranmu Edge Tape 21MM", "price": 15000, "stock": 0, "category": "Edge Tapes", "sku": "274112"},
    {"name": "Asunranmu Edge Tape 48MM", "price": 17000, "stock": 5, "category": "Edge Tapes", "sku": "275136"},
    {"name": "Bamboo Edge Tape 48MM", "price": 15000, "stock": 66, "category": "Edge Tapes", "sku": "354515"},
    {"name": "Beech Edge Tape 48MM", "price": 15000, "stock": 46, "category": "Edge Tapes", "sku": "354513"},
    {"name": "Biege Edge Tape 0.5x48MM", "price": 15000, "stock": 35, "category": "Edge Tapes", "sku": "274838"},
    {"name": "Biege Edge Tape 0.5x48MM Gloss", "price": 15500, "stock": 14, "category": "Edge Tapes", "sku": "274848"},
    {"name": "Biege Edge Tape 21MM", "price": 15000, "stock": 26, "category": "Edge Tapes", "sku": "273965"},
    {"name": "Biege Edge Tape 48MM", "price": 16000, "stock": 38, "category": "Edge Tapes", "sku": "274808"},
    {"name": "Black Edge Tape 0.5x48MM", "price": 16000, "stock": 10, "category": "Edge Tapes", "sku": "279610"},
    {"name": "Black Edge Tape 0.5x48MM Gloss", "price": 16500, "stock": 20, "category": "Edge Tapes", "sku": "279616"},
    {"name": "Black Edge Tape 21MM", "price": 15500, "stock": 17, "category": "Edge Tapes", "sku": "273959"},
    {"name": "Black Edge Tape 21MM Gloss", "price": 16000, "stock": 12, "category": "Edge Tapes", "sku": "273937"},
    {"name": "Black Edge Tape 48MM", "price": 14500, "stock": 58, "category": "Edge Tapes", "sku": "274850"},
    {"name": "Black Edge Tape 48MM Gloss", "price": 15500, "stock": 50, "category": "Edge Tapes", "sku": "275149"},
    {"name": "Brown Masonia Edge Tape 21MM Gloss", "price": 16000, "stock": 17, "category": "Edge Tapes", "sku": "274114"},
    {"name": "Brown Masonia Edge Tape 48MM", "price": 16000, "stock": 29, "category": "Edge Tapes", "sku": "275137"},
    {"name": "Cappuccino Edge Tape 0.5x48MM", "price": 15000, "stock": 10, "category": "Edge Tapes", "sku": "274830"},
    {"name": "Cappuccino Edge Tape 0.5x48MM Gloss", "price": 16500, "stock": 2, "category": "Edge Tapes", "sku": "279615"},
    {"name": "Cappuccino Edge Tape 21MM Gloss", "price": 16000, "stock": 2, "category": "Edge Tapes", "sku": "273934"},
    {"name": "Cappuccino Edge Tape 48MM", "price": 14500, "stock": 93, "category": "Edge Tapes", "sku": "274121"},
    {"name": "Cappuccino Edge Tape 48MM Gloss", "price": 15500, "stock": 59, "category": "Edge Tapes", "sku": "275147"},
    {"name": "Cedar Edge Tape 0.5x48MM", "price": 16000, "stock": 4, "category": "Edge Tapes", "sku": "279609"},
    {"name": "Cedar Edge Tape 0.5x48MM Gloss", "price": 16500, "stock": 12, "category": "Edge Tapes", "sku": "279612"},
    {"name": "Cedar Edge Tape 21MM Gloss", "price": 16000, "stock": 5, "category": "Edge Tapes", "sku": "274115"},
    {"name": "Cedar Edge Tape 48MM", "price": 15000, "stock": 85, "category": "Edge Tapes", "sku": "274854"},
    {"name": "Cedar Edge Tape 48MM Gloss", "price": 16500, "stock": 12, "category": "Edge Tapes", "sku": "275148"},
    {"name": "Codoba Edge Tape 21MM", "price": 15500, "stock": 20, "category": "Edge Tapes", "sku": "273855"},
    {"name": "Color 1123-1 Edge Tape 48MM", "price": 15000, "stock": 27, "category": "Edge Tapes", "sku": "354522"},
    {"name": "Color 40 Edge Tape 21MM", "price": 15500, "stock": 13, "category": "Edge Tapes", "sku": "273926"},
    {"name": "Color 40 Edge Tape 48MM", "price": 16000, "stock": 28, "category": "Edge Tapes", "sku": "275142"},
    {"name": "Color 5201 Edge Tape 48MM", "price": 17000, "stock": 5, "category": "Edge Tapes", "sku": "275143"},
    {"name": "Color 6200 Edge Tape 48MM", "price": 15000, "stock": 64, "category": "Edge Tapes", "sku": "354516"},
    {"name": "Color 6490 Edge Tape 48MM", "price": 16000, "stock": 1, "category": "Edge Tapes", "sku": "274857"},
    {"name": "Color 6655 Edge Tape 48MM", "price": 15000, "stock": 42, "category": "Edge Tapes", "sku": "354517"},
    {"name": "Akala Masonia Edge Tape 21MM", "price": 15523, "stock": 39, "category": "Edge Tapes", "sku": "273928"},
    {"name": "Akala Masonia Edge Tape 48MM", "price": 32000, "stock": 1, "category": "Edge Tapes", "sku": "273945"},
    {"name": "Akala Masonia Edge Tape 48MM Gloss", "price": 32000, "stock": 4, "category": "Edge Tapes", "sku": "273949"},
    {"name": "Color 7049 Edge Tape 48MM", "price": 15000, "stock": 37, "category": "Edge Tapes", "sku": "354518"},
    {"name": "Color 7469 Edge Tape 21MM", "price": 15523, "stock": 2, "category": "Edge Tapes", "sku": "273927"},
    {"name": "Color 7742 Edge Tape 21MM", "price": 15500, "stock": 21, "category": "Edge Tapes", "sku": "273930"},
    {"name": "Color 7742 Edge Tape 48MM", "price": 32000, "stock": 4, "category": "Edge Tapes", "sku": "273946"},
    {"name": "Color 7901 Edge Tape 21MM", "price": 15500, "stock": 18, "category": "Edge Tapes", "sku": "273933"},
    {"name": "Color 7901 Edge Tape 48MM", "price": 15500, "stock": 0, "category": "Edge Tapes", "sku": "273932"},
    {"name": "Customer Code Edge Tape 21MM", "price": 15500, "stock": 0, "category": "Edge Tapes", "sku": "277602"},
    {"name": "Customer Code Edge Tape 48MM", "price": 16000, "stock": 3, "category": "Edge Tapes", "sku": "274853"},
    {"name": "Dark Grey Edge Tape 0.5x48MM", "price": 15000, "stock": 18, "category": "Edge Tapes", "sku": "274836"},
    {"name": "Dark Grey Edge Tape 0.5x48MM Gloss", "price": 16500, "stock": 11, "category": "Edge Tapes", "sku": "274845"},
    {"name": "Dark Grey Edge Tape 21MM Gloss", "price": 16000, "stock": 24, "category": "Edge Tapes", "sku": "273939"},
    {"name": "Dark Grey Edge Tape 48MM", "price": 14500, "stock": 68, "category": "Edge Tapes", "sku": "274849"},
    {"name": "Dark Grey Edge Tape 48MM Gloss", "price": 15500, "stock": 42, "category": "Edge Tapes", "sku": "275150"},
    {"name": "Gold Edge Tape 48MM", "price": 39000, "stock": 144, "category": "Edge Tapes", "sku": "275151"},
    {"name": "Grey Edge Tape 0.5x48MM Gloss", "price": 16500, "stock": 14, "category": "Edge Tapes", "sku": "274844"},
    {"name": "Grey Edge Tape 21MM Gloss", "price": 16000, "stock": 2, "category": "Edge Tapes", "sku": "273935"},
    {"name": "Grey Edge Tape 48MM Gloss", "price": 16500, "stock": 4, "category": "Edge Tapes", "sku": "273954"},
    {"name": "HC059 Edge Tape 21MM", "price": 15500, "stock": 1, "category": "Edge Tapes", "sku": "273931"},
    {"name": "Light Dark Grey Edge Tape 0.5x48MM", "price": 15000, "stock": 27, "category": "Edge Tapes", "sku": "274837"},
    {"name": "Light Dark Grey Edge Tape 0.5x48MM Gloss", "price": 15500, "stock": 18, "category": "Edge Tapes", "sku": "274847"},
    {"name": "Light Dark Grey Edge Tape 0.5x48MM Gloss B", "price": 14250, "stock": 0, "category": "Edge Tapes", "sku": "274846"},
    {"name": "Light Dark Grey Edge Tape 21MM", "price": 15000, "stock": 11, "category": "Edge Tapes", "sku": "273966"},
    {"name": "Light Dark Grey Edge Tape 48MM", "price": 15500, "stock": 6, "category": "Edge Tapes", "sku": "274811"},
    {"name": "Light Grey Edge Tape 0.5x48MM", "price": 15000, "stock": 13, "category": "Edge Tapes", "sku": "274834"},
    {"name": "Light Grey Edge Tape 21MM", "price": 15000, "stock": 73, "category": "Edge Tapes", "sku": "273956"},
    {"name": "Light Grey Edge Tape 48MM", "price": 14500, "stock": 57, "category": "Edge Tapes", "sku": "274120"},
    {"name": "Light Grey Edge Tape 48MM Gloss", "price": 15500, "stock": 30, "category": "Edge Tapes", "sku": "354525"},
    {"name": "M4 Edge Tape 48MM", "price": 16500, "stock": 2, "category": "Edge Tapes", "sku": "274855"},
    {"name": "Marble Edge Tape 21MM", "price": 15500, "stock": 22, "category": "Edge Tapes", "sku": "273871"},
    {"name": "Marble Edge Tape 21MM Gloss", "price": 16000, "stock": 35, "category": "Edge Tapes", "sku": "274116"},
    {"name": "Marble Edge Tape 48MM", "price": 32000, "stock": 3, "category": "Edge Tapes", "sku": "273942"},
    {"name": "Marble Edge Tape 48MM Gloss", "price": 16000, "stock": 7, "category": "Edge Tapes", "sku": "274817"},
    {"name": "Masonia1 Edge Tape 48MM", "price": 16500, "stock": 0, "category": "Edge Tapes", "sku": "274860"},
    {"name": "Masonia4 Edge Tape 21MM", "price": 15000, "stock": 0, "category": "Edge Tapes", "sku": "274111"},
    {"name": "Masonia4 Edge Tape 48MM", "price": 15000, "stock": 87, "category": "Edge Tapes", "sku": "273862"},
    {"name": "New Cedar Edge Tape 48MM", "price": 15000, "stock": 54, "category": "Edge Tapes", "sku": "354511"},
    {"name": "Off White Edge Tape 0.5x48MM Gloss", "price": 16500, "stock": 11, "category": "Edge Tapes", "sku": "279614"},
    {"name": "Off White Edge Tape 21MM", "price": 15000, "stock": 1, "category": "Edge Tapes", "sku": "273958"},
    {"name": "Off White Edge Tape 21MM Gloss", "price": 16000, "stock": 5, "category": "Edge Tapes", "sku": "274119"},
    {"name": "Off White Edge Tape 48MM", "price": 16000, "stock": 32, "category": "Edge Tapes", "sku": "273940"},
    {"name": "Off White Edge Tape 48MM Gloss", "price": 15500, "stock": 67, "category": "Edge Tapes", "sku": "274821"},
    {"name": "Perfect White Edge Tape 21MM", "price": 15000, "stock": 46, "category": "Edge Tapes", "sku": "273964"},
    {"name": "Perfect White Edge Tape 21MM Gloss", "price": 16000, "stock": 1, "category": "Edge Tapes", "sku": "274117"},
    {"name": "Perfect White Edge Tape 48MM", "price": 16000, "stock": 5, "category": "Edge Tapes", "sku": "273941"},
    {"name": "Perfect White Edge Tape 48MM Gloss", "price": 16500, "stock": 3, "category": "Edge Tapes", "sku": "274818"},
    {"name": "Perfect White Edge Tape 0.5x48MM", "price": 16000, "stock": 1, "category": "Edge Tapes", "sku": "274827"},
    {"name": "Perfect White Edge Tape 0.5x48MM Gloss", "price": 16500, "stock": 13, "category": "Edge Tapes", "sku": "279613"},
    {"name": "Red Rose Edge Tape 0.5x48MM", "price": 16000, "stock": 11, "category": "Edge Tapes", "sku": "274824"},
    {"name": "Red Rose Edge Tape 0.5x48MM Gloss", "price": 16500, "stock": 11, "category": "Edge Tapes", "sku": "274843"},
    {"name": "Red Rose Edge Tape 21MM", "price": 15000, "stock": 0, "category": "Edge Tapes", "sku": "274110"},
    {"name": "Red Rose Edge Tape 48MM", "price": 16000, "stock": 1, "category": "Edge Tapes", "sku": "274814"},
    {"name": "Silver Edge Tape 21MM Gloss", "price": 30000, "stock": 24, "category": "Edge Tapes", "sku": "273936"},
    {"name": "Silver Grey Edge Tape 21MM", "price": 15500, "stock": 0, "category": "Edge Tapes", "sku": "273845"},
    {"name": "Silver Grey Edge Tape 48MM", "price": 16500, "stock": 1, "category": "Edge Tapes", "sku": "274856"},
    {"name": "Soldier Edge Tape 48MM", "price": 16000, "stock": 0, "category": "Edge Tapes", "sku": "275144"},
    {"name": "ST-7890 Edge Tape 48MM", "price": 15000, "stock": 45, "category": "Edge Tapes", "sku": "354519"},
    {"name": "ST-89 Edge Tape 48MM", "price": 15000, "stock": 43, "category": "Edge Tapes", "sku": "354521"},
    {"name": "St-z2 Edge Tape 21MM", "price": 15500, "stock": 6, "category": "Edge Tapes", "sku": "273925"},
    {"name": "ST-z2 Edge Tape 48MM", "price": 16000, "stock": 0, "category": "Edge Tapes", "sku": "274859"},
    {"name": "Switch Edge Tape 0.5x48MM", "price": 16000, "stock": 0, "category": "Edge Tapes", "sku": "279608"},
    {"name": "Switch Edge Tape 0.5x48MM Gloss", "price": 16500, "stock": 6, "category": "Edge Tapes", "sku": "279611"},
    {"name": "Switch Edge Tape 21MM Gloss", "price": 16000, "stock": 16, "category": "Edge Tapes", "sku": "274113"},
    {"name": "Switch Edge Tape 48MM", "price": 15000, "stock": 148, "category": "Edge Tapes", "sku": "274858"},
    {"name": "Switch Edge Tape 48MM Gloss", "price": 17000, "stock": 22, "category": "Edge Tapes", "sku": "275145"},
    {"name": "Wenge Edge Tape 0.5x48MM", "price": 16000, "stock": 4, "category": "Edge Tapes", "sku": "279605"},
    {"name": "Wenge Edge Tape 0.5x48MM Gloss", "price": 16500, "stock": 26, "category": "Edge Tapes", "sku": "274840"},
    {"name": "Wenge Edge Tape 21MM", "price": 15000, "stock": 7, "category": "Edge Tapes", "sku": "274109"},
    {"name": "Wenge Edge Tape 21MM Gloss", "price": 16000, "stock": 13, "category": "Edge Tapes", "sku": "273938"},
    {"name": "Wenge Edge Tape 48MM", "price": 15000, "stock": 105, "category": "Edge Tapes", "sku": "274852"},
    {"name": "Wenge Edge Tape 48MM Gloss", "price": 16500, "stock": 22, "category": "Edge Tapes", "sku": "275146"},
    {"name": "White Edge Tape 21MM", "price": 15000, "stock": 16, "category": "Edge Tapes", "sku": "273957"},
    {"name": "White Edge Tape 21MM Gloss", "price": 16000, "stock": 25, "category": "Edge Tapes", "sku": "274118"},
    {"name": "White Edge Tape 48MM Gloss", "price": 16500, "stock": 3, "category": "Edge Tapes", "sku": "273953"},
    {"name": "White Masonia Edge Tape 0.5x48MM", "price": 16000, "stock": 1, "category": "Edge Tapes", "sku": "279607"},
    {"name": "White Masonia Edge Tape 48MM", "price": 15000, "stock": 61, "category": "Edge Tapes", "sku": "275141"},
    {"name": "Zebrano Edge Tape 21MM", "price": 15500, "stock": 5, "category": "Edge Tapes", "sku": "273874"},
    {"name": "Zebrano Edge Tape 48MM", "price": 32000, "stock": 0, "category": "Edge Tapes", "sku": "273943"},
]


async def main() -> None:
    engine = create_async_engine(DATABASE_URL)
    async_session = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

    async with async_session() as db:
        # ── 1. Delete all existing data (order matters for FK constraints) ──
        print("Clearing all data...")
        await db.execute(text("DELETE FROM sale_audit_entries"))
        await db.execute(text("DELETE FROM sale_bulk_upload_jobs"))
        await db.execute(text("DELETE FROM sales"))
        await db.execute(text("DELETE FROM order_payments"))
        await db.execute(text("DELETE FROM order_status_history"))
        await db.execute(text("DELETE FROM order_line_items"))
        await db.execute(text("DELETE FROM purchase_orders"))
        await db.execute(text("DELETE FROM stock_movements"))
        await db.execute(text("DELETE FROM inventory_batches"))
        await db.execute(text("DELETE FROM inventory_levels"))
        await db.execute(text("DELETE FROM price_history"))
        await db.execute(text("DELETE FROM products"))
        await db.execute(text("DELETE FROM product_categories"))
        await db.commit()
        print("All data cleared.")

        # ── 2. Create categories ────────────────────────────────────────────
        print("Creating categories...")
        cat_map: dict[str, uuid.UUID] = {}
        for cat in CATEGORIES:
            cat_id = uuid.uuid4()
            cat_map[cat["name"]] = cat_id
            await db.execute(
                text(
                    "INSERT INTO product_categories (id, name, description) "
                    "VALUES (:id, :name, :desc)"
                ),
                {"id": cat_id, "name": cat["name"], "desc": cat["description"]},
            )
        await db.commit()
        print(f"  {len(CATEGORIES)} categories created.")

        # ── 3. Create products + inventory ──────────────────────────────────
        print("Creating products...")
        now = datetime.now(timezone.utc)
        # Get a user ID to attribute actions to
        user_row = await db.execute(text("SELECT id FROM users LIMIT 1"))
        user = user_row.scalar_one_or_none()
        if not user:
            print("ERROR: No user found. Register a user first.")
            return

        created = 0
        for p in PRODUCTS:
            pid = uuid.uuid4()
            cat_id = cat_map.get(p["category"])
            selling = Decimal(str(p["price"]))

            await db.execute(
                text(
                    "INSERT INTO products "
                    "(id, name, sku, category_id, unit_cost, selling_price, currency, is_active, created_at, updated_at) "
                    "VALUES (:id, :name, :sku, :cat, :cost, :sell, 'NGN', true, :now, :now)"
                ),
                {
                    "id": pid,
                    "name": p["name"],
                    "sku": p["sku"],
                    "cat": cat_id,
                    "cost": Decimal("0"),
                    "sell": selling,
                    "now": now,
                },
            )

            # Price history
            await db.execute(
                text(
                    "INSERT INTO price_history "
                    "(id, product_id, old_unit_cost, new_unit_cost, old_selling_price, new_selling_price, "
                    "reason, effective_date, changed_by) "
                    "VALUES (:id, :pid, 0, 0, :sell, :sell, 'Initial seed', :today, :uid)"
                ),
                {"id": uuid.uuid4(), "pid": pid, "sell": selling, "today": date.today(), "uid": user},
            )

            # Inventory level
            stock = p["stock"]
            await db.execute(
                text(
                    "INSERT INTO inventory_levels "
                    "(id, product_id, quantity_on_hand, quantity_reserved, low_stock_threshold, created_at, updated_at) "
                    "VALUES (:id, :pid, :qty, 0, 10, :now, :now)"
                ),
                {"id": uuid.uuid4(), "pid": pid, "qty": stock, "now": now},
            )

            # Stock movement if stock > 0
            if stock > 0:
                await db.execute(
                    text(
                        "INSERT INTO stock_movements "
                        "(id, product_id, movement_type, quantity_change, quantity_before, quantity_after, "
                        "reason, performed_by) "
                        "VALUES (:id, :pid, 'MANUAL_ADD', :qty, 0, :qty, 'Initial seed stock', :uid)"
                    ),
                    {"id": uuid.uuid4(), "pid": pid, "qty": stock, "uid": user},
                )

            created += 1

        await db.commit()
        print(f"  {created} products created with inventory.")

    await engine.dispose()
    print("\nSeed complete!")


if __name__ == "__main__":
    asyncio.run(main())
