"""Products API routes."""

import os
import uuid

import anyio
from fastapi import APIRouter, Depends, HTTPException, Query, UploadFile, status
from sqlalchemy.ext.asyncio import AsyncSession

from src.auth.dependencies import get_current_active_user
from src.auth.models import User
from src.core.database import get_db
from src.products.exceptions import (
    CategoryInUseError,
    CategoryNotFoundError,
    DuplicateSKUError,
    ProductNotFoundError,
)
from src.products.schemas import (
    BulkProductUploadResponse,
    BulkUploadRowError,
    CategoryCreate,
    CategoryRead,
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
    update_product,
)

router = APIRouter()


# ---------------------------------------------------------------------------
# Categories
# ---------------------------------------------------------------------------


@router.post("/categories", response_model=CategoryRead, status_code=status.HTTP_201_CREATED)
async def create_category_endpoint(
    body: CategoryCreate,
    db: AsyncSession = Depends(get_db),
    _current_user: User = Depends(get_current_active_user),
):
    """Create a new product category."""
    return await create_category(db, body)


@router.get("/categories", response_model=list[CategoryRead])
async def list_categories_endpoint(db: AsyncSession = Depends(get_db)):
    """List all product categories."""
    return await list_categories(db)


@router.delete("/categories/{category_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_category_endpoint(
    category_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    _current_user: User = Depends(get_current_active_user),
):
    """Delete a category (only if no products linked)."""
    try:
        await delete_category(db, category_id)
    except CategoryNotFoundError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))
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
):
    """Create a new product."""
    try:
        product = await create_product(db, body, current_user.id)
    except CategoryNotFoundError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
    except DuplicateSKUError as e:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(e))
    return product


@router.post("/bulk-upload", response_model=BulkProductUploadResponse)
async def bulk_upload_products_endpoint(
    file: UploadFile,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    """Bulk-create products from a CSV or Excel file.

    Required columns: name, unit_cost, selling_price
    Optional columns: sku, description, category, currency
    """
    import csv
    import io
    from decimal import Decimal, InvalidOperation

    import structlog

    logger = structlog.get_logger()

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
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Empty CSV file")
        rows = list(reader)
    else:
        try:
            import openpyxl
        except ImportError:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Excel support requires openpyxl. Please upload a CSV file instead.",
            )
        wb = openpyxl.load_workbook(io.BytesIO(contents), read_only=True, data_only=True)
        ws = wb.active
        if ws is None:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Empty workbook")
        all_rows = list(ws.iter_rows(values_only=True))
        if len(all_rows) < 2:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="File has no data rows")
        headers = [str(h or "").strip().lower() for h in all_rows[0]]
        for data_row in all_rows[1:]:
            rows.append({headers[i]: str(v or "").strip() for i, v in enumerate(data_row) if i < len(headers)})

    # Normalise header names (allow common variations)
    HEADER_MAP = {
        "product name": "name", "product_name": "name",
        "cost": "unit_cost", "cost_price": "unit_cost", "cost price": "unit_cost",
        "price": "selling_price", "sell_price": "selling_price", "sell price": "selling_price",
        "selling price": "selling_price", "selling_price": "selling_price",
        "unit cost": "unit_cost", "unit_cost": "unit_cost",
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
    categories = await list_categories(db)
    cat_map = {c.name.lower(): c.id for c in categories}

    errors: list[BulkUploadRowError] = []
    created_ids: list[uuid.UUID] = []

    for i, row in enumerate(normalised, start=2):  # row 1 = header
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
                    new_cat = await create_category(db, CategoryCreate(name=cat_name))
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
            product = await create_product(db, data, current_user.id)
            created_ids.append(product.id)
        except (ValueError, InvalidOperation) as e:
            errors.append(BulkUploadRowError(row=i, error=str(e)))
        except DuplicateSKUError as e:
            errors.append(BulkUploadRowError(row=i, error=str(e)))
        except Exception as e:
            errors.append(BulkUploadRowError(row=i, error=str(e)))

    await logger.ainfo(
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
):
    """List products with filtering and pagination."""
    items, total = await list_products(
        db,
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
):
    """Get a single product by ID."""
    try:
        return await get_product(db, product_id)
    except ProductNotFoundError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))


@router.put("/{product_id}", response_model=ProductRead)
async def update_product_endpoint(
    product_id: uuid.UUID,
    body: ProductUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    """Update a product."""
    try:
        return await update_product(db, product_id, body, current_user.id)
    except ProductNotFoundError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))
    except CategoryNotFoundError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))


@router.delete("/{product_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_product_endpoint(
    product_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    _current_user: User = Depends(get_current_active_user),
):
    """Soft-delete a product."""
    try:
        await deactivate_product(db, product_id)
    except ProductNotFoundError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))


@router.get("/{product_id}/price-history", response_model=list[PriceHistoryRead])
async def get_price_history_endpoint(
    product_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
):
    """Get price change history for a product."""
    try:
        return await get_price_history(db, product_id)
    except ProductNotFoundError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))


@router.post("/{product_id}/image", response_model=ProductRead)
async def upload_product_image(
    product_id: uuid.UUID,
    file: UploadFile,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    """Upload or replace a product image."""
    ALLOWED_EXTENSIONS = {".jpg", ".jpeg", ".png", ".webp"}
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

    upload_dir = os.path.join(os.environ.get("UPLOAD_DIR", "/uploads"), "products")
    os.makedirs(upload_dir, exist_ok=True)
    upload_path = f"{upload_dir}/{product_id}{ext}"

    def _write() -> None:
        with open(upload_path, "wb") as f_out:
            f_out.write(contents)

    await anyio.to_thread.run_sync(_write)

    image_url = f"/static/products/{product_id}{ext}"
    update_data = ProductUpdate(image_url=image_url)
    try:
        return await update_product(db, product_id, update_data, current_user.id)
    except ProductNotFoundError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))
