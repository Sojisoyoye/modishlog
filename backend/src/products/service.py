"""Products domain business logic."""

import uuid
from datetime import date

import structlog
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from src.inventory.service import initialize_inventory
from src.products.exceptions import (
    CategoryInUseError,
    CategoryNotFoundError,
    DuplicateSKUError,
    ProductNotFoundError,
)
from src.products.models import PriceHistory, Product, ProductCategory
from src.products.schemas import (
    CategoryCreate,
    CategoryUpdate,
    ProductCreate,
    ProductUpdate,
)

logger = structlog.get_logger()


# ---------------------------------------------------------------------------
# SKU generation
# ---------------------------------------------------------------------------


async def _generate_sku(db: AsyncSession) -> str:
    """Auto-generate a unique SKU like PRD-00001."""
    result = await db.execute(select(func.count()).select_from(Product))
    count = result.scalar() or 0
    while True:
        count += 1
        sku = f"PRD-{count:05d}"
        existing = await db.execute(select(Product).where(Product.sku == sku))
        if not existing.scalar_one_or_none():
            return sku


# ---------------------------------------------------------------------------
# Category CRUD
# ---------------------------------------------------------------------------


async def create_category(
    db: AsyncSession,
    data: CategoryCreate,
) -> ProductCategory:
    """Create a product category."""
    category = ProductCategory(name=data.name, description=data.description)
    db.add(category)
    await db.flush()
    await logger.ainfo("category_created", category_id=str(category.id), name=data.name)
    return category


async def list_categories(db: AsyncSession) -> list[ProductCategory]:
    """List all product categories ordered by name."""
    result = await db.execute(select(ProductCategory).order_by(ProductCategory.name))
    return list(result.scalars().all())


async def get_category(db: AsyncSession, category_id: uuid.UUID) -> ProductCategory:
    """Get a category by ID."""
    category = await db.get(ProductCategory, category_id)
    if not category:
        raise CategoryNotFoundError(category_id)
    return category


async def delete_category(db: AsyncSession, category_id: uuid.UUID) -> None:
    """Delete a category (only if no products are linked)."""
    category = await get_category(db, category_id)
    result = await db.execute(
        select(func.count())
        .select_from(Product)
        .where(Product.category_id == category_id)
    )
    count = result.scalar() or 0
    if count > 0:
        raise CategoryInUseError(category_id, count)
    await db.delete(category)
    await db.flush()


async def update_category(
    db: AsyncSession,
    category_id: uuid.UUID,
    data: CategoryUpdate,
) -> ProductCategory:
    """Update a category's name and/or description."""
    category = await get_category(db, category_id)
    if data.name is not None:
        category.name = data.name
    if "description" in data.model_fields_set:
        category.description = data.description
    await db.flush()
    await logger.ainfo("category_updated", category_id=str(category_id))
    return category


# ---------------------------------------------------------------------------
# Product CRUD
# ---------------------------------------------------------------------------


async def create_product(
    db: AsyncSession,
    data: ProductCreate,
    user_id: uuid.UUID,
) -> Product:
    """Create a new product, auto-generating SKU if not provided."""
    # Validate category exists (only if provided)
    if data.category_id is not None:
        await get_category(db, data.category_id)

    sku = data.sku
    if not sku:
        sku = await _generate_sku(db)
    else:
        existing = await db.execute(select(Product).where(Product.sku == sku))
        if existing.scalar_one_or_none():
            raise DuplicateSKUError(sku)

    product = Product(
        name=data.name,
        sku=sku,
        description=data.description,
        category_id=data.category_id,
        unit_cost=data.unit_cost,
        selling_price=data.selling_price,
        currency=data.currency,
        is_active=True,
    )
    db.add(product)
    await db.flush()

    # Create initial price history entry
    price_history = PriceHistory(
        product_id=product.id,
        old_unit_cost=data.unit_cost,
        new_unit_cost=data.unit_cost,
        old_selling_price=data.selling_price,
        new_selling_price=data.selling_price,
        reason="Initial product creation",
        effective_date=date.today(),
        changed_by=user_id,
    )
    db.add(price_history)
    await db.flush()

    # Initialize inventory level so sales/stock adjustments can work
    await initialize_inventory(db, product.id, user_id)

    await logger.ainfo("product_created", product_id=str(product.id), sku=sku)
    return product


async def get_product(db: AsyncSession, product_id: uuid.UUID) -> Product:
    """Get a single product by ID with category loaded."""
    result = await db.execute(
        select(Product)
        .options(selectinload(Product.category))
        .where(Product.id == product_id)
    )
    product = result.scalar_one_or_none()
    if not product:
        raise ProductNotFoundError(product_id=product_id)
    return product


async def list_products(
    db: AsyncSession,
    *,
    category_id: uuid.UUID | None = None,
    is_active: bool | None = True,
    search: str | None = None,
    page: int = 1,
    page_size: int = 20,
) -> tuple[list[Product], int]:
    """List products with filtering and pagination."""
    query = select(Product).options(selectinload(Product.category))
    count_query = select(func.count()).select_from(Product)

    if category_id is not None:
        query = query.where(Product.category_id == category_id)
        count_query = count_query.where(Product.category_id == category_id)
    if is_active is not None:
        query = query.where(Product.is_active == is_active)
        count_query = count_query.where(Product.is_active == is_active)
    if search:
        pattern = f"%{search}%"
        query = query.where(Product.name.ilike(pattern))
        count_query = count_query.where(Product.name.ilike(pattern))

    total_result = await db.execute(count_query)
    total = total_result.scalar() or 0

    offset = (page - 1) * page_size
    query = query.order_by(Product.name).offset(offset).limit(page_size)
    result = await db.execute(query)
    items = list(result.scalars().all())

    return items, total


async def update_product(
    db: AsyncSession,
    product_id: uuid.UUID,
    data: ProductUpdate,
    user_id: uuid.UUID,
) -> Product:
    """Update a product. Creates PriceHistory if prices change."""
    product = await get_product(db, product_id)

    update_fields = data.model_dump(exclude_unset=True)

    # Track price changes
    price_changed = False
    old_unit_cost = product.unit_cost
    old_selling_price = product.selling_price

    if "unit_cost" in update_fields and update_fields["unit_cost"] != old_unit_cost:
        price_changed = True
    if (
        "selling_price" in update_fields
        and update_fields["selling_price"] != old_selling_price
    ):
        price_changed = True

    # Validate category if changing
    if "category_id" in update_fields and update_fields["category_id"] is not None:
        await get_category(db, update_fields["category_id"])

    # Apply updates
    for field, value in update_fields.items():
        setattr(product, field, value)
    await db.flush()

    # Create price history if prices changed
    if price_changed:
        price_history = PriceHistory(
            product_id=product.id,
            old_unit_cost=old_unit_cost,
            new_unit_cost=product.unit_cost,
            old_selling_price=old_selling_price,
            new_selling_price=product.selling_price,
            reason="Product update",
            effective_date=date.today(),
            changed_by=user_id,
        )
        db.add(price_history)
        await db.flush()

    await logger.ainfo("product_updated", product_id=str(product_id))
    return product


async def deactivate_product(db: AsyncSession, product_id: uuid.UUID) -> Product:
    """Soft-delete a product by setting is_active=False."""
    product = await get_product(db, product_id)
    product.is_active = False
    await db.flush()
    await logger.ainfo("product_deactivated", product_id=str(product_id))
    return product


# ---------------------------------------------------------------------------
# Price history
# ---------------------------------------------------------------------------


async def get_price_history(
    db: AsyncSession,
    product_id: uuid.UUID,
) -> list[PriceHistory]:
    """Get price change history for a product."""
    await get_product(db, product_id)  # ensure product exists
    result = await db.execute(
        select(PriceHistory)
        .where(PriceHistory.product_id == product_id)
        .order_by(PriceHistory.effective_date.desc())
    )
    return list(result.scalars().all())
