"""Load layer — FK-ordered inserts, migration_id tagging, rollback.

Scope note: Phase 0 wires up the entities the spec calls out as needing
dedup/ghost-record/variant logic (categories, products, variants, suppliers,
customers, locations, sales). Every other importable table already has its
`migration_id` column (added by this same migration) so future work can
extend `LOAD_ORDER` without another schema change.
"""

import uuid

from sqlalchemy import delete, inspect
from sqlalchemy.ext.asyncio import AsyncSession

from src.customers.models import Customer
from src.data_import.etl.transformer import IdMap
from src.locations.models import BusinessLocation
from src.products.models import Product, ProductCategory, ProductVariant
from src.sales.models import Sale
from src.suppliers.models import Supplier

# FK dependency order — parents before children.
LOAD_ORDER: list[tuple[str, type]] = [
    ("product_categories", ProductCategory),
    ("products", Product),
    ("product_variants", ProductVariant),
    ("suppliers", Supplier),
    ("customers", Customer),
    ("business_locations", BusinessLocation),
    ("sales", Sale),
]


async def load(
    db: AsyncSession,
    migration_id: uuid.UUID,
    transformed: dict[str, list[dict]],
    id_map: IdMap,
) -> dict[str, int]:
    """Insert every transformed row in FK order, tagging each with migration_id.

    Atomicity is provided by the caller's request-scoped session (see
    `core/database.get_db`), which rolls back entirely on any exception — the
    confirm endpoint is the only caller, so no other code path can trigger a
    partial load.
    """
    row_counts: dict[str, int] = {}
    for entity, model_cls in LOAD_ORDER:
        rows = transformed.get(entity, [])
        valid_columns = {c.name for c in inspect(model_cls).columns}
        objs = []
        source_ids = []
        for row in rows:
            row = dict(row)
            source_ids.append(row.pop("_source_id", None))
            kwargs = {k: v for k, v in row.items() if k in valid_columns}
            kwargs["migration_id"] = migration_id
            objs.append(model_cls(**kwargs))
        if objs:
            db.add_all(objs)
            # Ids are pre-assigned by the transformer (see Transformer._assign_id),
            # so one flush per entity is enough — no need to flush per row to
            # discover generated PKs.
            await db.flush()
            for obj, source_id in zip(objs, source_ids):
                if source_id:
                    id_map.register(entity, source_id, obj.id)
        row_counts[entity] = len(objs)
    return row_counts


async def rollback(db: AsyncSession, migration_id: uuid.UUID) -> dict[str, int]:
    """Delete every row tagged with this migration_id, in reverse FK order."""
    deleted_counts: dict[str, int] = {}
    for entity, model_cls in reversed(LOAD_ORDER):
        result = await db.execute(delete(model_cls).where(model_cls.migration_id == migration_id))
        deleted_counts[entity] = result.rowcount
    return deleted_counts
