"""Load-test data seeder (task #243).

Seeds the docker-compose.loadtest.yml Postgres instance with a realistic
multi-tenant data volume: many businesses (one per simulated concurrent
trader), each with hundreds of products and thousands of historical sales --
matching the row counts flagged as risky in the scalability audit (an
empty-DB load test would miss exactly the problems already found in tasks
215/222/228).

Run against the loadtest stack only:
    DATABASE_URL=postgresql+asyncpg://modishlog:modishlog_dev@localhost:5436/modishlog_loadtest \
    backend/.venv/bin/python backend/scripts/loadtest_seed.py

Writes credentials for all seeded businesses to loadtest_users.json next to
this script, for the locustfile to read.
"""

import asyncio
import json
import os
import random
import sys
import uuid
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from sqlalchemy import insert, select  # noqa: E402
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine  # noqa: E402
from sqlalchemy.orm import sessionmaker  # noqa: E402

# Import the full app first so every model module (and therefore every FK
# string reference between them, e.g. users.migration_id -> migration_jobs)
# is registered on the shared declarative mapper before any flush -- this
# script only touches a handful of domains directly, but SQLAlchemy resolves
# FK strings against the whole registry, not just what's imported below.
import src.main  # noqa: E402,F401

from src.auth.models import Business, User, UserRole  # noqa: E402
from src.core.security import get_password_hash  # noqa: E402
from src.inventory.models import InventoryLevel  # noqa: E402
from src.products.models import Product, ProductCategory  # noqa: E402
from src.sales.models import Sale, SaleChannel, SaleStatus  # noqa: E402

DATABASE_URL = os.environ["DATABASE_URL"]

N_BUSINESSES = 30
PRODUCTS_PER_BUSINESS = 300
SALES_PER_BUSINESS = 2500
SEED_PASSWORD = "LoadTest123!"

CATEGORY_NAMES = ["Boards", "Doors", "Edge Tapes", "Hardware", "Panels"]
PRODUCT_ADJECTIVES = ["Black", "White", "Grey", "Cappuccino", "Oak", "Walnut", "Cedar", "Marble"]
PRODUCT_NOUNS = ["Board", "Door", "Tape", "Panel", "Hinge", "Handle", "Sheet", "Frame"]


def _random_business_name(i: int) -> str:
    return f"Loadtest Traders {i:03d}"


async def seed_business(db: AsyncSession, index: int) -> dict:
    business = Business(name=_random_business_name(index), currency="NGN")
    db.add(business)
    await db.flush()

    owner = User(
        email=f"loadtest.biz{index}@modishlog-loadtest.com",
        hashed_password=get_password_hash(SEED_PASSWORD),
        full_name=f"Loadtest Owner {index}",
        role=UserRole.OWNER,
        business_id=business.id,
        email_verified=True,
        is_active=True,
        ndpr_consent_given=True,
        ndpr_consent_at=datetime.now(timezone.utc),
    )
    db.add(owner)
    await db.flush()

    # Categories
    category_ids = []
    for name in CATEGORY_NAMES:
        cat_id = uuid.uuid4()
        category_ids.append(cat_id)
    await db.execute(
        insert(ProductCategory),
        [
            {"id": cid, "business_id": business.id, "name": name}
            for cid, name in zip(category_ids, CATEGORY_NAMES)
        ],
    )

    # Products + inventory levels
    now = datetime.now(timezone.utc)
    product_rows = []
    inventory_rows = []
    product_ids = []
    for p in range(PRODUCTS_PER_BUSINESS):
        pid = uuid.uuid4()
        product_ids.append(pid)
        adj = random.choice(PRODUCT_ADJECTIVES)
        noun = random.choice(PRODUCT_NOUNS)
        name = f"{adj} {noun} {p:04d}"
        cost = Decimal(random.randint(2000, 40000))
        margin = Decimal(str(random.uniform(1.15, 1.6)))
        sell = (cost * margin).quantize(Decimal("1"))
        product_rows.append(
            {
                "id": pid,
                "business_id": business.id,
                "name": name,
                "sku": f"LT-{index:03d}-{p:04d}",
                "slug": f"lt-{index:03d}-{p:04d}",
                "category_id": random.choice(category_ids),
                "unit_cost": cost,
                "selling_price": sell,
                "currency": "NGN",
                "is_active": True,
            }
        )
        inventory_rows.append(
            {
                "id": uuid.uuid4(),
                "product_id": pid,
                "variant_id": None,
                "quantity_on_hand": random.randint(0, 500),
                "quantity_reserved": 0,
                "low_stock_threshold": 10,
                "created_at": now,
                "updated_at": now,
            }
        )
    await db.execute(insert(Product), product_rows)
    await db.execute(insert(InventoryLevel), inventory_rows)

    # Sales — spread over the last 365 days, referencing this business's products only
    sale_rows = []
    today = date.today()
    for s in range(SALES_PER_BUSINESS):
        pid = random.choice(product_ids)
        qty = random.randint(1, 5)
        unit_price = Decimal(random.randint(2000, 60000))
        sale_date = today - timedelta(days=random.randint(0, 365))
        sale_rows.append(
            {
                "id": uuid.uuid4(),
                "business_id": business.id,
                "product_id": pid,
                "quantity": qty,
                "unit_price": unit_price,
                "total_amount": unit_price * qty,
                "currency": "NGN",
                "sale_date": sale_date,
                "channel": random.choice(list(SaleChannel)),
                "status": SaleStatus.COMPLETED,
                "recorded_by": owner.id,
                "payment_status": "paid",
            }
        )
    # Batch the insert to keep any single statement from getting too large.
    for i in range(0, len(sale_rows), 1000):
        await db.execute(insert(Sale), sale_rows[i : i + 1000])

    await db.commit()
    return {
        "business_id": str(business.id),
        "business_name": business.name,
        "email": owner.email,
        "password": SEED_PASSWORD,
        # A sample of this business's own product ids, for the locustfile's
        # bulk-upload scenario -- product_id must belong to the logged-in
        # business (create_sale scopes the lookup by business_id).
        "product_ids": [str(pid) for pid in product_ids[:50]],
    }


async def main() -> None:
    engine = create_async_engine(DATABASE_URL)
    async_session = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

    credentials = []
    async with async_session() as db:
        existing = await db.execute(select(Business.id).limit(1))
        if existing.scalar_one_or_none() is not None:
            print(
                "ERROR: target database already has data. This script is meant to run "
                "once against a freshly created docker-compose.loadtest.yml volume — "
                "refusing to seed on top of existing rows to avoid duplicate/mixed data."
            )
            await engine.dispose()
            return

    for i in range(N_BUSINESSES):
        async with async_session() as db:
            creds = await seed_business(db, i)
            credentials.append(creds)
        print(f"  seeded business {i + 1}/{N_BUSINESSES}: {creds['business_name']}")

    out_path = os.path.join(os.path.dirname(__file__), "..", "loadtest", "loadtest_users.json")
    os.makedirs(os.path.dirname(out_path), exist_ok=True)
    with open(out_path, "w") as f:
        json.dump(credentials, f, indent=2)

    await engine.dispose()
    print(
        f"\nSeed complete: {N_BUSINESSES} businesses, "
        f"{N_BUSINESSES * PRODUCTS_PER_BUSINESS} products, "
        f"{N_BUSINESSES * SALES_PER_BUSINESS} sales.\n"
        f"Credentials written to {out_path}"
    )


if __name__ == "__main__":
    asyncio.run(main())
