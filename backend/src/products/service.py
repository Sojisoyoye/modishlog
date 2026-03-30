# TODO: Async service functions for the Products domain
#
# --- Product CRUD ---
# async def create_product(db, product_in: ProductCreate, user_id: UUID) -> Product
#   - Validate category exists
#   - Auto-generate SKU if not provided (format: CAT-XXXXX)
#   - Ensure SKU uniqueness
#   - Create product record
#   - Create initial PriceHistory entry
#
# async def get_product(db, product_id: UUID) -> Product
#   - Fetch product with category relationship loaded
#   - Raise ProductNotFoundError if missing
#
# async def list_products(db, filters: dict, page: int, page_size: int) -> tuple[list[Product], int]
#   - Support filtering by: category_id, is_active, name (partial match), price range
#   - Paginate results
#   - Return (items, total_count)
#
# async def update_product(db, product_id: UUID, product_in: ProductUpdate, user_id: UUID) -> Product
#   - Fetch existing product, raise ProductNotFoundError if missing
#   - If price or cost changed, create PriceHistory entry
#   - Apply partial updates
#
# async def delete_product(db, product_id: UUID) -> None
#   - Soft-delete: set is_active = False
#   - Raise ProductNotFoundError if missing
#
# --- SKU Management ---
# async def generate_sku(db, product_id: UUID) -> str
#   - Build SKU from category prefix + sequential number
#   - Ensure uniqueness
#
# async def lookup_by_sku(db, sku: str) -> Product
#   - Find product by SKU, raise ProductNotFoundError if missing
#
# --- Categories ---
# async def create_category(db, category_in: CategoryCreate) -> ProductCategory
# async def list_categories(db) -> list[ProductCategory]
# async def update_category(db, cat_id: UUID, category_in: CategoryCreate) -> ProductCategory
# async def delete_category(db, cat_id: UUID) -> None
#   - Raise CategoryInUseError if products are linked
#
# --- Price / Cost Tracking ---
# async def get_price_history(db, product_id: UUID) -> list[PriceHistory]
#   - Return chronologically sorted price changes
#
# async def record_price_change(db, product_id: UUID, update: PriceUpdateCreate, user_id: UUID) -> PriceHistory
#   - Snapshot old values, apply new values, log change
#
# async def get_margin_report(db) -> list[MarginReport]
#   - Compute margin for each active product
#   - Sort by margin_pct descending
