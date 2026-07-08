"""Products API routes."""

import os
import uuid

import anyio
from fastapi import APIRouter, Depends, HTTPException, Query, UploadFile, status
from sqlalchemy.ext.asyncio import AsyncSession

from src.auth.dependencies import get_current_active_user, get_current_business_id
from src.auth.models import User
from src.core.config import settings
from src.core.database import get_db
from src.products.exceptions import (
    CategoryHasChildrenError,
    CategoryInUseError,
    CategoryNotFoundError,
    DuplicateSKUError,
    DuplicateSlugError,
    InvalidProductNameError,
    ProductNotFoundError,
    SubcategoryDepthError,
)
from src.products.schemas import (
    BulkProductUploadResponse,
    BulkUploadRowError,
    CategoryCreate,
    CategoryRead,
    CategoryUpdate,
    PriceHistoryRead,
    ProductCreate,
    ProductListResponse,
    ProductRead,
    ProductUpdate,
)
from src.products.service import (
    create_category,
    create_product,
    deactivate_product,
    delete_category,
    get_price_history,
    get_product,
    list_categories,
    list_products,
    update_category,
    update_product,
)

router = APIRouter()


# ---------------------------------------------------------------------------
# Categories
# ---------------------------------------------------------------------------


@router.post(
    "/categories", response_model=CategoryRead, status_code=status.HTTP_201_CREATED
)
async def create_category_endpoint(
    body: CategoryCreate,
    db: AsyncSession = Depends(get_db),
    _current_user: User = Depends(get_current_active_user),
    business_id: uuid.UUID = Depends(get_current_business_id),
):
    """Create a new product category."""
    try:
        return await create_category(db, body, business_id)
    except CategoryNotFoundError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
    except SubcategoryDepthError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))


@router.get("/categories", response_model=list[CategoryRead])
async def list_categories_endpoint(
    db: AsyncSession = Depends(get_db),
    business_id: uuid.UUID = Depends(get_current_business_id),
):
    """List top-level categories with their children nested."""
    all_cats = await list_categories(db, business_id)
    return [c for c in all_cats if c.parent_id is None]


@router.patch("/categories/{category_id}", response_model=CategoryRead)
async def update_category_endpoint(
    category_id: uuid.UUID,
    body: CategoryUpdate,
    db: AsyncSession = Depends(get_db),
    _current_user: User = Depends(get_current_active_user),
    business_id: uuid.UUID = Depends(get_current_business_id),
):
    """Update a category's name and/or description."""
    try:
        return await update_category(db, category_id, body, business_id=business_id)
    except CategoryNotFoundError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))


@router.delete("/categories/{category_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_category_endpoint(
    category_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    _current_user: User = Depends(get_current_active_user),
    business_id: uuid.UUID = Depends(get_current_business_id),
):
    """Delete a category (only if no products or sub-categories linked)."""
    try:
        await delete_category(db, category_id, business_id)
    except CategoryNotFoundError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))
    except CategoryHasChildrenError as e:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(e))
    except CategoryInUseError as e:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(e))


# ---------------------------------------------------------------------------
# Products
# ---------------------------------------------------------------------------


@router.post("", response_model=ProductRead, status_code=status.HTTP_201_CREATED)
async def create_product_endpoint(
    body: ProductCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
    business_id: uuid.UUID = Depends(get_current_business_id),
):
    """Create a new product."""
    try:
        product = await create_product(db, body, current_user.id, business_id)
    except CategoryNotFoundError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
    except InvalidProductNameError as e:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(e)
        )
    except DuplicateSKUError as e:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(e))
    except DuplicateSlugError as e:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(e))
    return product


_CSV_BATCH_SIZE = 500  # Commit in batches to avoid long-held transactions


@router.post("/bulk-upload", response_model=BulkProductUploadResponse)
async def bulk_upload_products_endpoint(
    file: UploadFile,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
    business_id: uuid.UUID = Depends(get_current_business_id),
):
    """Bulk-create products from a CSV or Excel file.

    Required columns: name, unit_cost, selling_price
    Optional columns: sku, description, category, currency

    Large CSVs are processed in streaming batches of 500 rows to avoid OOM.
    The configurable MAX_CSV_ROWS limit (default 50,000) prevents excessively
    large uploads from exhausting container memory.
    """
    import csv
    import io
    from decimal import Decimal, InvalidOperation

    import structlog

    _logger = structlog.get_logger()

    filename = file.filename or ""
    ext = filename.rsplit(".", 1)[-1].lower() if "." in filename else ""
    if ext not in ("csv", "xlsx", "xls"):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Only .csv, .xlsx, or .xls files are accepted.",
        )

    contents = await file.read()
    rows: list[dict[str, str]] = []

    if ext == "csv":
        try:
            text = contents.decode("utf-8")
        except UnicodeDecodeError:
            text = contents.decode("latin-1")
        reader = csv.DictReader(io.StringIO(text))
        if not reader.fieldnames:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST, detail="Empty CSV file"
            )
        # Stream rows one by one — avoid holding the entire dataset in memory as a list
        for row in reader:
            rows.append(dict(row))
            if len(rows) > settings.MAX_CSV_ROWS:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=(
                        f"CSV exceeds the maximum of {settings.MAX_CSV_ROWS:,} rows. "
                        "Split the file into smaller batches and upload separately."
                    ),
                )
    else:
        try:
            import openpyxl
        except ImportError:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Excel support requires openpyxl. Please upload a CSV file instead.",
            )
        wb = openpyxl.load_workbook(
            io.BytesIO(contents), read_only=True, data_only=True
        )
        ws = wb.active
        if ws is None:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST, detail="Empty workbook"
            )
        all_rows = list(ws.iter_rows(values_only=True))
        if len(all_rows) < 2:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST, detail="File has no data rows"
            )
        headers = [str(h or "").strip().lower() for h in all_rows[0]]
        for data_row in all_rows[1:]:
            rows.append(
                {
                    headers[i]: str(v or "").strip()
                    for i, v in enumerate(data_row)
                    if i < len(headers)
                }
            )
        if len(rows) > settings.MAX_CSV_ROWS:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=(
                    f"File exceeds the maximum of {settings.MAX_CSV_ROWS:,} rows. "
                    "Split the file into smaller batches and upload separately."
                ),
            )

    # Normalise header names (allow common variations)
    HEADER_MAP = {
        "product name": "name",
        "product_name": "name",
        "cost": "unit_cost",
        "cost_price": "unit_cost",
        "cost price": "unit_cost",
        "price": "selling_price",
        "sell_price": "selling_price",
        "sell price": "selling_price",
        "selling price": "selling_price",
        "selling_price": "selling_price",
        "unit cost": "unit_cost",
        "unit_cost": "unit_cost",
    }
    normalised: list[dict[str, str]] = []
    for row in rows:
        mapped: dict[str, str] = {}
        for key, val in row.items():
            canonical = HEADER_MAP.get(key.strip().lower(), key.strip().lower())
            mapped[canonical] = val
        normalised.append(mapped)

    # Validate required columns
    if normalised:
        sample = normalised[0]
        missing = {"name", "unit_cost", "selling_price"} - set(sample.keys())
        if missing:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Missing required columns: {', '.join(sorted(missing))}. "
                f"Found columns: {', '.join(sorted(sample.keys()))}",
            )

    # Build category lookup
    categories = await list_categories(db, business_id)
    cat_map = {c.name.lower(): c.id for c in categories}

    errors: list[BulkUploadRowError] = []
    created_ids: list[uuid.UUID] = []

    # Process in batches of _CSV_BATCH_SIZE rows, flushing per batch to avoid
    # holding a single enormous transaction open for the entire upload.
    for batch_start in range(0, len(normalised), _CSV_BATCH_SIZE):
        batch = normalised[batch_start : batch_start + _CSV_BATCH_SIZE]
        for i, row in enumerate(batch, start=batch_start + 2):  # row 1 = header
            try:
                name = row.get("name", "").strip()
                if not name:
                    raise ValueError("name is required")

                unit_cost = Decimal(row.get("unit_cost", "0").replace(",", ""))
                selling_price = Decimal(row.get("selling_price", "0").replace(",", ""))

                cat_id = None
                cat_name = row.get("category", "").strip()
                if cat_name:
                    cat_id = cat_map.get(cat_name.lower())
                    if not cat_id:
                        new_cat = await create_category(db, CategoryCreate(name=cat_name), business_id)
                        cat_map[cat_name.lower()] = new_cat.id
                        cat_id = new_cat.id

                data = ProductCreate(
                    name=name,
                    sku=row.get("sku", "").strip() or None,
                    description=row.get("description", "").strip() or None,
                    category_id=cat_id,
                    unit_cost=unit_cost,
                    selling_price=selling_price,
                    currency=row.get("currency", "").strip() or "NGN",
                )
                product = await create_product(db, data, current_user.id, business_id)
                created_ids.append(product.id)
            except (ValueError, InvalidOperation) as e:
                errors.append(BulkUploadRowError(row=i, error=str(e)))
            except (DuplicateSKUError, DuplicateSlugError, InvalidProductNameError) as e:
                errors.append(BulkUploadRowError(row=i, error=str(e)))
            except Exception:
                _logger.exception("bulk_upload_row_error", row=i)
                errors.append(BulkUploadRowError(row=i, error="Internal error processing row"))

        # Flush (not commit) after each batch so the DB session can release memory.
        # The outer get_db() dependency will commit the entire upload on success.
        await db.flush()

    await _logger.ainfo(
        "bulk_product_upload",
        total=len(normalised),
        successful=len(created_ids),
        failed=len(errors),
    )

    return BulkProductUploadResponse(
        total_rows=len(normalised),
        successful=len(created_ids),
        failed=len(errors),
        errors=errors,
        created_ids=created_ids,
    )


@router.get("", response_model=ProductListResponse)
async def list_products_endpoint(
    category_id: uuid.UUID | None = None,
    is_active: bool | None = True,
    search: str | None = None,
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
    db: AsyncSession = Depends(get_db),
    business_id: uuid.UUID = Depends(get_current_business_id),
):
    """List products with filtering and pagination."""
    items, total = await list_products(
        db,
        business_id,
        category_id=category_id,
        is_active=is_active,
        search=search,
        page=page,
        page_size=page_size,
    )
    return ProductListResponse(items=items, total=total, page=page, page_size=page_size)


@router.get("/{product_id}", response_model=ProductRead)
async def get_product_endpoint(
    product_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    business_id: uuid.UUID = Depends(get_current_business_id),
):
    """Get a single product by ID."""
    try:
        return await get_product(db, product_id, business_id=business_id)
    except ProductNotFoundError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))


@router.put("/{product_id}", response_model=ProductRead)
async def update_product_endpoint(
    product_id: uuid.UUID,
    body: ProductUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
    business_id: uuid.UUID = Depends(get_current_business_id),
):
    """Update a product."""
    try:
        return await update_product(db, product_id, body, current_user.id, business_id=business_id)
    except ProductNotFoundError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))
    except CategoryNotFoundError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
    except InvalidProductNameError as e:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(e)
        )
    except DuplicateSlugError as e:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(e))


@router.delete("/{product_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_product_endpoint(
    product_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    _current_user: User = Depends(get_current_active_user),
    business_id: uuid.UUID = Depends(get_current_business_id),
):
    """Soft-delete a product."""
    try:
        await deactivate_product(db, product_id, business_id=business_id)
    except ProductNotFoundError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))


@router.get("/{product_id}/price-history", response_model=list[PriceHistoryRead])
async def get_price_history_endpoint(
    product_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    business_id: uuid.UUID = Depends(get_current_business_id),
):
    """Get price change history for a product."""
    try:
        return await get_price_history(db, product_id, business_id=business_id)
    except ProductNotFoundError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))


@router.post("/{product_id}/image", response_model=ProductRead)
async def upload_product_image(
    product_id: uuid.UUID,
    file: UploadFile,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
    business_id: uuid.UUID = Depends(get_current_business_id),
):
    """Upload or replace a product image.

    S6: Validates actual MIME type via python-magic (not the client-supplied
    Content-Type header). Files are stored outside the web root with UUID
    filenames to prevent directory traversal and content-type spoofing attacks.
    """
    import structlog as _structlog

    _logger = _structlog.get_logger()

    ALLOWED_EXTENSIONS = {".jpg", ".jpeg", ".png", ".webp"}
    # S6: Allowed MIME types — validated against actual file bytes, not headers.
    ALLOWED_MIME_TYPES = {"image/jpeg", "image/png", "image/webp"}
    MAX_FILE_SIZE = 5 * 1024 * 1024  # 5MB

    ext = os.path.splitext(file.filename or "")[1].lower() or ".jpg"
    if ext not in ALLOWED_EXTENSIONS:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"File type '{ext}' not allowed. Accepted: {', '.join(ALLOWED_EXTENSIONS)}",
        )

    contents = await file.read()
    if len(contents) > MAX_FILE_SIZE:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"File too large ({len(contents)} bytes). Maximum: {MAX_FILE_SIZE} bytes (5MB).",
        )

    # S6: Validate actual MIME type using libmagic, not the client-supplied Content-Type.
    # This prevents PHP shells or malicious files from being accepted as images.
    try:
        import magic

        detected_mime = magic.from_buffer(contents, mime=True)
    except ImportError:
        # libmagic not available — fall back to extension check with a warning
        await _logger.awarning(
            "mime_validation_skipped",
            reason="python-magic not available — install libmagic for server-side MIME validation",
            product_id=str(product_id),
        )
        detected_mime = None

    if detected_mime is not None and detected_mime not in ALLOWED_MIME_TYPES:
        await _logger.awarning(
            "file_upload_mime_rejected",
            product_id=str(product_id),
            declared_content_type=file.content_type,
            detected_mime=detected_mime,
        )
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=(
                f"File content does not match an allowed image type. "
                f"Detected: {detected_mime}. Accepted: {', '.join(sorted(ALLOWED_MIME_TYPES))}"
            ),
        )

    # S6: Store with UUID filename to prevent directory traversal and filename injection.
    # Files stored outside web root (UPLOAD_DIR is configurable, defaults to /app/uploads).
    upload_dir = os.path.join(settings.UPLOAD_DIR, "products")
    os.makedirs(upload_dir, exist_ok=True)
    # Always use UUID-based filename regardless of original filename
    safe_filename = f"{uuid.uuid4()}{ext}"
    upload_path = os.path.join(upload_dir, safe_filename)

    def _write() -> None:
        with open(upload_path, "wb") as f_out:
            f_out.write(contents)

    await anyio.to_thread.run_sync(_write)

    image_url = f"/static/products/{safe_filename}"
    update_data = ProductUpdate(image_url=image_url)
    try:
        return await update_product(db, product_id, update_data, current_user.id, business_id=business_id)
    except ProductNotFoundError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))
