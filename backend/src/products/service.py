"""Products domain business logic."""

import uuid
from datetime import date
from decimal import Decimal

import structlog
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from src.inventory.service import initialize_inventory
from src.products.exceptions import (
    CategoryHasChildrenError,
    CategoryInUseError,
    CategoryNotFoundError,
    DuplicateSKUError,
    DuplicateSlugError,
    InvalidProductNameError,
    ProductNotFoundError,
    SubcategoryDepthError,
    VariantNotFoundError,
)
from src.products.utils import slugify
from src.products.models import PriceHistory, Product, ProductCategory, ProductVariant
from src.products.schemas import (
    CategoryCreate,
    CategoryUpdate,
    ProductCreate,
    ProductUpdate,
    ProductVariantCreate,
    ProductVariantUpdate,
)

logger = structlog.get_logger()


# ---------------------------------------------------------------------------
# SKU generation
# ---------------------------------------------------------------------------


async def _generate_sku(db: AsyncSession, business_id: uuid.UUID) -> str:
    """Auto-generate a unique SKU like PRD-00001, scoped to the given business."""
    result = await db.execute(
        select(func.count()).select_from(Product).where(Product.business_id == business_id)
    )
    count = result.scalar() or 0
    while True:
        count += 1
        sku = f"PRD-{count:05d}"
        existing = await db.execute(
            select(Product).where(Product.sku == sku, Product.business_id == business_id)
        )
        if not existing.scalar_one_or_none():
            return sku


# ---------------------------------------------------------------------------
# Category CRUD
# ---------------------------------------------------------------------------


async def create_category(
    db: AsyncSession,
    data: CategoryCreate,
    business_id: uuid.UUID,
) -> ProductCategory:
    """Create a product category, optionally nested under a parent (max 2 levels)."""
    if data.parent_id is not None:
        parent = await db.get(ProductCategory, data.parent_id)
        if not parent:
            raise CategoryNotFoundError(data.parent_id)
        if parent.business_id != business_id:
            raise CategoryNotFoundError(data.parent_id)
        if parent.parent_id is not None:
            raise SubcategoryDepthError(data.parent_id)

    category = ProductCategory(
        name=data.name,
        description=data.description,
        parent_id=data.parent_id,
        default_margin_pct=data.default_margin_pct,
        business_id=business_id,
    )
    db.add(category)
    await db.flush()
    await logger.ainfo("category_created", category_id=str(category.id), name=data.name)
    # Reload with children relationship to satisfy lazy='raise' during serialization
    result = await db.execute(
        select(ProductCategory)
        .options(selectinload(ProductCategory.children))
        .where(ProductCategory.id == category.id)
    )
    return result.scalar_one()


async def list_categories(db: AsyncSession, business_id: uuid.UUID) -> list[ProductCategory]:
    """List all product categories for a business ordered by name, with children pre-loaded."""
    result = await db.execute(
        select(ProductCategory)
        .options(selectinload(ProductCategory.children))
        .where(ProductCategory.business_id == business_id)
        .order_by(ProductCategory.name)
    )
    return list(result.scalars().all())


async def get_category(
    db: AsyncSession,
    category_id: uuid.UUID,
    business_id: uuid.UUID | None = None,
) -> ProductCategory:
    """Get a category by ID. If business_id is provided, verifies ownership."""
    category = await db.get(ProductCategory, category_id)
    if not category:
        raise CategoryNotFoundError(category_id)
    if business_id is not None and category.business_id != business_id:
        raise CategoryNotFoundError(category_id)
    return category


async def delete_category(
    db: AsyncSession,
    category_id: uuid.UUID,
    business_id: uuid.UUID,
) -> None:
    """Delete a category (only if no products or sub-categories are linked)."""
    category = await get_category(db, category_id, business_id=business_id)
    child_result = await db.execute(
        select(func.count())
        .select_from(ProductCategory)
        .where(ProductCategory.parent_id == category_id)
    )
    child_count = child_result.scalar() or 0
    if child_count > 0:
        raise CategoryHasChildrenError(category_id, child_count)
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
    business_id: uuid.UUID | None = None,
) -> ProductCategory:
    """Update a category's name and/or description."""
    category = await get_category(db, category_id, business_id=business_id)
    if data.name is not None:
        category.name = data.name
    if "description" in data.model_fields_set:
        category.description = data.description
    if "default_margin_pct" in data.model_fields_set:
        category.default_margin_pct = data.default_margin_pct
    await db.flush()
    await logger.ainfo("category_updated", category_id=str(category_id))
    # Reload with children relationship to satisfy lazy='raise' during serialization
    result = await db.execute(
        select(ProductCategory)
        .options(selectinload(ProductCategory.children))
        .where(ProductCategory.id == category_id)
    )
    return result.scalar_one()


# ---------------------------------------------------------------------------
# Product CRUD
# ---------------------------------------------------------------------------


async def create_product(
    db: AsyncSession,
    data: ProductCreate,
    user_id: uuid.UUID,
    business_id: uuid.UUID,
) -> Product:
    """Create a new product, auto-generating SKU if not provided."""
    # Validate category exists and belongs to this business (only if provided)
    if data.category_id is not None:
        await get_category(db, data.category_id, business_id=business_id)

    sku = data.sku
    if not sku:
        sku = await _generate_sku(db, business_id)
    else:
        existing = await db.execute(
            select(Product).where(Product.sku == sku, Product.business_id == business_id)
        )
        if existing.scalar_one_or_none():
            raise DuplicateSKUError(sku)

    slug = slugify(data.name)
    if not slug:
        raise InvalidProductNameError(
            data.name,
            "produces an empty slug — use a name with at least one alphanumeric character",
        )
    existing_slug = await db.execute(
        select(Product).where(Product.slug == slug, Product.business_id == business_id)
    )
    if existing_slug.scalar_one_or_none():
        raise DuplicateSlugError(slug)

    product = Product(
        name=data.name,
        sku=sku,
        slug=slug,
        description=data.description,
        category_id=data.category_id,
        unit_cost=data.unit_cost,
        selling_price=data.selling_price,
        currency=data.currency,
        is_active=True,
        business_id=business_id,
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


async def get_product(
    db: AsyncSession,
    product_id: uuid.UUID,
    business_id: uuid.UUID | None = None,
) -> Product:
    """Get a single product by ID with category loaded.

    If business_id is provided, only returns products belonging to that business.
    """
    conditions = [Product.id == product_id]
    if business_id is not None:
        conditions.append(Product.business_id == business_id)

    result = await db.execute(
        select(Product)
        .options(selectinload(Product.category))
        .where(*conditions)
    )
    product = result.scalar_one_or_none()
    if not product:
        raise ProductNotFoundError(product_id=product_id)
    return product


async def list_products(
    db: AsyncSession,
    business_id: uuid.UUID,
    *,
    category_id: uuid.UUID | None = None,
    is_active: bool | None = True,
    search: str | None = None,
    page: int = 1,
    page_size: int = 20,
) -> tuple[list[Product], int]:
    """List products with filtering and pagination, scoped to a business."""
    query = select(Product).options(selectinload(Product.category))
    count_query = select(func.count()).select_from(Product)

    # Always filter by business_id for data isolation
    query = query.where(Product.business_id == business_id)
    count_query = count_query.where(Product.business_id == business_id)

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
    business_id: uuid.UUID | None = None,
) -> Product:
    """Update a product. Creates PriceHistory if prices change."""
    product = await get_product(db, product_id, business_id=business_id)

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

    # Validate category if changing — also verify it belongs to this business
    if "category_id" in update_fields and update_fields["category_id"] is not None:
        await get_category(db, update_fields["category_id"], business_id=business_id)

    # Regenerate slug when name changes
    if "name" in update_fields:
        new_slug = slugify(update_fields["name"])
        if not new_slug:
            raise InvalidProductNameError(
                update_fields["name"],
                "produces an empty slug — use a name with at least one alphanumeric character",
            )
        if new_slug != product.slug:
            conflict = await db.execute(
                select(Product).where(
                    Product.slug == new_slug,
                    Product.id != product_id,
                    Product.business_id == business_id,
                )
            )
            if conflict.scalar_one_or_none():
                raise DuplicateSlugError(new_slug)
            update_fields["slug"] = new_slug

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


async def deactivate_product(
    db: AsyncSession,
    product_id: uuid.UUID,
    business_id: uuid.UUID | None = None,
) -> Product:
    """Soft-delete a product by setting is_active=False."""
    product = await get_product(db, product_id, business_id=business_id)
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
    business_id: uuid.UUID | None = None,
) -> list[PriceHistory]:
    """Get price change history for a product."""
    await get_product(db, product_id, business_id=business_id)  # ensure product exists and is owned
    result = await db.execute(
        select(PriceHistory)
        .where(PriceHistory.product_id == product_id)
        .order_by(PriceHistory.effective_date.desc())
    )
    return list(result.scalars().all())


# ---------------------------------------------------------------------------
# Variant helpers
# ---------------------------------------------------------------------------


def resolve_price(product: Product, variant: ProductVariant | None) -> Decimal:
    """Return the effective selling price, preferring variant override when set."""
    if variant and variant.price_override is not None:
        return variant.price_override
    return product.selling_price


def resolve_cost(product: Product, variant: ProductVariant | None) -> Decimal:
    """Return the effective cost price, preferring variant override when set."""
    if variant and variant.cost_price_override is not None:
        return variant.cost_price_override
    return product.unit_cost


# ---------------------------------------------------------------------------
# Variant CRUD
# ---------------------------------------------------------------------------


async def create_variant(
    db: AsyncSession,
    product_id: uuid.UUID,
    data: ProductVariantCreate,
    business_id: uuid.UUID,
) -> ProductVariant:
    """Create a product variant and mark the parent product as having variants."""
    # Verify product exists and belongs to business
    product = await get_product(db, product_id, business_id=business_id)

    # Check SKU uniqueness within the business when provided (guard against empty string too)
    if data.sku is not None and data.sku != "":
        existing = await db.execute(
            select(ProductVariant).where(
                ProductVariant.sku == data.sku,
                ProductVariant.business_id == business_id,
            )
        )
        if existing.scalar_one_or_none():
            raise DuplicateSKUError(data.sku)

    variant = ProductVariant(
        product_id=product_id,
        business_id=business_id,
        name=data.name,
        sku=data.sku or None,  # normalize empty string to NULL
        barcode=data.barcode or None,  # normalize empty string to NULL
        attributes=data.attributes,
        price_override=data.price_override,
        cost_price_override=data.cost_price_override,
        is_active=True,
    )
    db.add(variant)

    # Mark parent product as having variants
    product.has_variants = True

    await db.flush()
    await logger.ainfo(
        "variant_created",
        variant_id=str(variant.id),
        product_id=str(product_id),
    )
    return variant


async def list_variants(
    db: AsyncSession,
    product_id: uuid.UUID,
    business_id: uuid.UUID,
) -> list[ProductVariant]:
    """List all variants for a product scoped to the given business."""
    result = await db.execute(
        select(ProductVariant)
        .where(
            ProductVariant.product_id == product_id,
            ProductVariant.business_id == business_id,
        )
        .order_by(ProductVariant.created_at)
    )
    return list(result.scalars().all())


async def update_variant(
    db: AsyncSession,
    product_id: uuid.UUID,
    variant_id: uuid.UUID,
    data: ProductVariantUpdate,
    business_id: uuid.UUID,
) -> ProductVariant:
    """Update a product variant."""
    result = await db.execute(
        select(ProductVariant).where(
            ProductVariant.id == variant_id,
            ProductVariant.product_id == product_id,
            ProductVariant.business_id == business_id,
        )
    )
    variant = result.scalar_one_or_none()
    if not variant:
        raise VariantNotFoundError(variant_id)

    update_fields = data.model_dump(exclude_unset=True)
    for field, value in update_fields.items():
        setattr(variant, field, value)

    await db.flush()
    await logger.ainfo("variant_updated", variant_id=str(variant_id))
    return variant


async def deactivate_variant(
    db: AsyncSession,
    product_id: uuid.UUID,
    variant_id: uuid.UUID,
    business_id: uuid.UUID,
) -> None:
    """Soft-delete a variant by setting is_active=False."""
    result = await db.execute(
        select(ProductVariant).where(
            ProductVariant.id == variant_id,
            ProductVariant.product_id == product_id,
            ProductVariant.business_id == business_id,
        )
    )
    variant = result.scalar_one_or_none()
    if not variant:
        raise VariantNotFoundError(variant_id)

    variant.is_active = False
    await db.flush()
    await logger.ainfo("variant_deactivated", variant_id=str(variant_id))
