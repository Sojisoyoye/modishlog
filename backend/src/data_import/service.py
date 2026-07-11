"""Data import (ETL) orchestration — glues extractor → transformer → validator
→ loader together behind the job lifecycle described in the router.
"""

import csv
import io
import json
import os
import uuid
from datetime import datetime, timezone

import anyio
import structlog
from pydantic import ValidationError as PydanticValidationError
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.config import settings
from src.data_import.etl.adapters.registry import API_ADAPTERS, CSV_ADAPTERS
from src.data_import.etl.extractor import CSVExtractor
from src.data_import.etl.loader import load as loader_load
from src.data_import.etl.loader import (
    load_purchase_orders as loader_load_purchase_orders,
)
from src.data_import.etl.loader import rollback as loader_rollback
from src.data_import.etl.transformer import Transformer
from src.data_import.etl.validator import validate_extracted_data
from src.data_import.exceptions import (
    InvalidJobStateError,
    MigrationJobNotFoundError,
    MissingExtractedDataError,
    PurchaseOrderImportError,
    UnsupportedSourceSystemError,
)
from src.data_import.models import (
    ExtractionMode,
    MigrationJob,
    MigrationJobStatus,
    SourceSystem,
)
from src.data_import.schemas import (
    ConfirmationSnapshot,
    SnapshotEntity,
    ValidationIssue,
)
from src.inventory.exceptions import (
    InvalidStockAdjustmentError,
    ProductStockNotFoundError,
)
from src.orders.exceptions import (
    InvalidStatusTransitionError,
    OrderLineItemError,
    OrderNotFoundError,
)

logger = structlog.get_logger()

# Entities the frontend wizard can upload / the ETL pipeline fully loads. Every
# other importable table already has a `migration_id` column ready for when
# loader.LOAD_ORDER is extended.
IMPORTABLE_ENTITIES = [
    "product_categories",
    "products",
    "product_variants",
    "suppliers",
    "customers",
    "business_locations",
    "purchase_orders",
    "sales",
]

_SAMPLE_ROWS = 3


def _job_upload_dir(job_id: uuid.UUID) -> str:
    return os.path.join(settings.UPLOAD_DIR, "imports", str(job_id))


def _job_extracted_json_path(job_id: uuid.UUID) -> str:
    return os.path.join(_job_upload_dir(job_id), "extracted.json")


def _save_extracted_data_sync(job_id: uuid.UUID, data: dict) -> None:
    path = _job_extracted_json_path(job_id)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w") as f:
        json.dump(data, f)


async def _save_extracted_data(job_id: uuid.UUID, data: dict) -> None:
    await anyio.to_thread.run_sync(_save_extracted_data_sync, job_id, data)


def _load_extracted_data_sync(job_id: uuid.UUID) -> dict:
    path = _job_extracted_json_path(job_id)
    if not os.path.isfile(path):
        return {}
    with open(path) as f:
        return json.load(f)


async def _load_extracted_data(job_id: uuid.UUID) -> dict:
    return await anyio.to_thread.run_sync(_load_extracted_data_sync, job_id)


async def create_job(
    db: AsyncSession,
    *,
    business_id: uuid.UUID,
    user_id: uuid.UUID,
    source_system: SourceSystem,
    extraction_mode: ExtractionMode,
    files: dict[str, bytes] | None = None,
    api_base_url: str | None = None,
    credentials: dict[str, str] | None = None,
) -> MigrationJob:
    job = MigrationJob(
        business_id=business_id,
        created_by=user_id,
        source_system=source_system,
        extraction_mode=extraction_mode,
        api_base_url=api_base_url,
        status=MigrationJobStatus.PENDING,
    )
    db.add(job)
    await db.flush()

    if extraction_mode == ExtractionMode.CSV and files:
        upload_dir = _job_upload_dir(job.id)

        def _write_all() -> None:
            os.makedirs(upload_dir, exist_ok=True)
            for entity, raw_bytes in files.items():
                with open(os.path.join(upload_dir, f"{entity}.csv"), "wb") as f:
                    f.write(raw_bytes)

        await anyio.to_thread.run_sync(_write_all)

    elif extraction_mode == ExtractionMode.API:
        adapter_cls = API_ADAPTERS.get(source_system.value)
        if adapter_cls is None:
            raise UnsupportedSourceSystemError(source_system.value, "api")

        # Credentials are used only for this one pull, right now, then
        # discarded — they are never written to the DB or logged. What DOES
        # get persisted is the *extracted data* (already plain strings, same
        # shape CSV extraction produces), so validate/confirm/snapshot can
        # re-read it later without ever needing credentials again.
        job.status = MigrationJobStatus.EXTRACTING
        extractor = adapter_cls(api_base_url, credentials or {})
        try:
            extracted = await extractor.extract()
        except Exception:
            # Must commit (not just flush) — the exception we're about to
            # re-raise propagates through get_db's `except: rollback()`,
            # which would otherwise wipe out this job row entirely, along
            # with the FAILED status meant to record the failed attempt.
            job.status = MigrationJobStatus.FAILED
            await db.commit()
            raise
        await _save_extracted_data(job.id, extracted)
        job.row_counts = {entity: len(rows) for entity, rows in extracted.items()}
        job.status = MigrationJobStatus.PENDING

    logger.info(
        "data_import_job_created", job_id=str(job.id), source_system=source_system.value
    )
    return job


async def list_jobs(db: AsyncSession, *, business_id: uuid.UUID) -> list[MigrationJob]:
    result = await db.execute(
        select(MigrationJob)
        .where(MigrationJob.business_id == business_id)
        .order_by(MigrationJob.created_at.desc())
    )
    return result.scalars().all()


async def get_job(
    db: AsyncSession, job_id: uuid.UUID, *, business_id: uuid.UUID
) -> MigrationJob:
    result = await db.execute(
        select(MigrationJob).where(
            MigrationJob.id == job_id, MigrationJob.business_id == business_id
        )
    )
    job = result.scalar_one_or_none()
    if job is None:
        raise MigrationJobNotFoundError(job_id)
    return job


def _load_saved_csv_files_sync(job_id: uuid.UUID) -> dict[str, bytes]:
    upload_dir = _job_upload_dir(job_id)
    if not os.path.isdir(upload_dir):
        return {}
    files: dict[str, bytes] = {}
    for filename in os.listdir(upload_dir):
        if filename.endswith(".csv"):
            with open(os.path.join(upload_dir, filename), "rb") as f:
                files[filename[: -len(".csv")]] = f.read()
    return files


async def _load_saved_csv_files(job_id: uuid.UUID) -> dict[str, bytes]:
    return await anyio.to_thread.run_sync(_load_saved_csv_files_sync, job_id)


async def _extract_and_transform(
    db: AsyncSession, job: MigrationJob
) -> tuple[dict[str, list[dict]], dict[str, list[dict]], Transformer]:
    """Returns (mapped_raw_rows, transformed_rows, transformer) so the caller
    can validate structural issues on the mapped raw rows and pull
    dedup/ghost-record warnings off the transformer.

    Known tech debt: validate/snapshot/confirm each call this from scratch —
    every call re-reads the cached extraction and re-runs every dedup query.
    That's correct (each call sees current DB state) but means three full
    passes for one job, and a duplicate created between snapshot and confirm
    could make the two disagree. Acceptable for Phase 0/1's scale; a caching
    layer for the *transform* step is the fix if that becomes a problem.
    """
    if job.extraction_mode == ExtractionMode.API:
        # Extraction already happened once, at job-creation time (see
        # create_job) — credentials aren't available here and don't need to
        # be; the extracted rows are already in target field-name shape
        # (the API extractor did its own mapping), so no adapter.map_rows()
        # step is needed, unlike CSV mode below.
        mapped: dict[str, list[dict]] = await _load_extracted_data(job.id)
        if not mapped:
            # A missing cache must never silently degrade to "0 rows,
            # validation passed" — that's a zero-row import masquerading as
            # a success. create_job always writes this cache on success (and
            # fails the job outright otherwise), so an empty result here
            # means something is genuinely wrong with the job's state.
            raise MissingExtractedDataError(job.id)
    else:
        csv_adapter_cls = CSV_ADAPTERS.get(
            job.source_system.value, CSV_ADAPTERS["generic"]
        )
        csv_adapter = csv_adapter_cls()

        raw_files = await _load_saved_csv_files(job.id)
        extractor = CSVExtractor(raw_files)
        raw = await extractor.extract()

        mapped = {
            entity: csv_adapter.map_rows(entity, rows) for entity, rows in raw.items()
        }

    transformer = Transformer(db, job.business_id, job.created_by)

    known_product_ids = {
        r.get("source_id") for r in mapped.get("products", []) if r.get("source_id")
    }
    ghosts = transformer.detect_ghost_products(
        mapped.get("sales", []), known_product_ids
    )

    transformed: dict[str, list[dict]] = {
        "product_categories": await transformer.transform_categories(
            mapped.get("product_categories", [])
        ),
        "products": await transformer.transform_products(
            mapped.get("products", []) + ghosts
        ),
        "suppliers": await transformer.transform_suppliers(mapped.get("suppliers", [])),
        "customers": await transformer.transform_customers(mapped.get("customers", [])),
        "business_locations": transformer.transform_locations(
            mapped.get("business_locations", [])
        ),
    }
    transformed["product_variants"] = await transformer.transform_variants(
        mapped.get("product_variants", [])
    )

    location_map = {}
    for row in transformed["business_locations"]:
        location_map[row["name"]] = row["id"]
        if row.get("_source_id"):
            location_map[row["_source_id"]] = row["id"]

    transformed["sales"] = transformer.transform_sales(
        mapped.get("sales", []), location_map
    )
    transformed["purchase_orders"] = transformer.transform_purchase_orders(
        mapped.get("purchase_orders", [])
    )

    return mapped, transformed, transformer


async def validate_job(db: AsyncSession, job: MigrationJob) -> MigrationJob:
    mapped, transformed, transformer = await _extract_and_transform(db, job)

    issues: list[ValidationIssue] = validate_extracted_data(mapped)
    issues.extend(transformer.warnings)

    errors = [i for i in issues if i.severity == "error"]
    job.validation_errors = [i.model_dump() for i in issues if i.severity == "error"]
    job.validation_warnings = [
        i.model_dump() for i in issues if i.severity == "warning"
    ]
    job.row_counts = {entity: len(rows) for entity, rows in transformed.items()}
    job.status = (
        MigrationJobStatus.AWAITING_CONFIRMATION
        if not errors
        else MigrationJobStatus.TRANSFORMING
    )
    await db.flush()
    return job


async def build_confirmation_snapshot(
    db: AsyncSession, job: MigrationJob
) -> ConfirmationSnapshot:
    if job.status != MigrationJobStatus.AWAITING_CONFIRMATION:
        raise InvalidJobStateError(job.id, "awaiting_confirmation", job.status.value)

    _mapped, transformed, transformer = await _extract_and_transform(db, job)

    ghost_count = sum(
        1
        for row in transformed.get("products", [])
        if str(row.get("name", "")).startswith("[Deleted Product:")
    )

    entities = [
        SnapshotEntity(
            name=entity,
            count=len(rows),
            sample_rows=[
                {k: str(v) for k, v in r.items() if not k.startswith("_")}
                for r in rows[:_SAMPLE_ROWS]
            ],
        )
        for entity, rows in transformed.items()
    ]

    return ConfirmationSnapshot(
        job_id=job.id,
        extraction_mode=job.extraction_mode,
        source_system=job.source_system,
        status=job.status,
        entities=entities,
        warnings=transformer.warnings,
        ghost_records={"products": ghost_count} if ghost_count else {},
        total_rows=sum(len(rows) for rows in transformed.values()),
    )


async def confirm_job(
    db: AsyncSession, job: MigrationJob, *, approved: bool
) -> MigrationJob:
    if job.status != MigrationJobStatus.AWAITING_CONFIRMATION:
        raise InvalidJobStateError(job.id, "awaiting_confirmation", job.status.value)

    if not approved:
        job.status = MigrationJobStatus.CANCELLED
        await db.flush()
        return job

    job.status = MigrationJobStatus.IMPORTING
    _mapped, transformed, transformer = await _extract_and_transform(db, job)
    row_counts = await loader_load(db, job.id, transformed, transformer.id_map)
    try:
        row_counts["purchase_orders"] = await loader_load_purchase_orders(
            db,
            job.id,
            job.business_id,
            job.created_by,
            transformed.get("purchase_orders", []),
        )
    except (
        OrderLineItemError,
        OrderNotFoundError,
        InvalidStatusTransitionError,
        ProductStockNotFoundError,
        InvalidStockAdjustmentError,
        PydanticValidationError,
    ) as e:
        # load_purchase_orders() reuses the orders/inventory services
        # unmodified — translate whatever they raise into this domain's own
        # exception so the router (and any other caller) only needs to know
        # about one data_import-owned exception type, not every exception
        # those unrelated domains happen to raise today.
        raise PurchaseOrderImportError(e) from e

    job.row_counts = row_counts
    job.status = MigrationJobStatus.DONE
    job.completed_at = datetime.now(timezone.utc)
    await db.flush()
    logger.info("data_import_job_confirmed", job_id=str(job.id), row_counts=row_counts)
    return job


async def rollback_job(db: AsyncSession, job: MigrationJob) -> MigrationJob:
    if job.status != MigrationJobStatus.DONE:
        raise InvalidJobStateError(job.id, "done", job.status.value)

    deleted_counts = await loader_rollback(db, job.id)
    job.status = MigrationJobStatus.ROLLED_BACK
    await db.flush()
    logger.info(
        "data_import_job_rolled_back", job_id=str(job.id), deleted_counts=deleted_counts
    )
    return job


# ---------------------------------------------------------------------------
# CSV templates
# ---------------------------------------------------------------------------

_TEMPLATE_COLUMNS: dict[str, list[str]] = {
    "product_categories": ["source_id", "name", "description", "parent_source_id"],
    "products": [
        "source_id",
        "name",
        "sku",
        "barcode",
        "unit_cost",
        "selling_price",
        "currency",
        "category_source_id",
        "is_active",
    ],
    "product_variants": [
        "source_id",
        "product_source_id",
        "name",
        "sku",
        "barcode",
        "attributes",
        "price_override",
        "cost_price_override",
    ],
    "suppliers": ["source_id", "name", "email", "contact_person", "mobile"],
    "customers": ["source_id", "name", "email", "contact_number"],
    "business_locations": ["source_id", "name", "location_code"],
    "purchase_orders": [
        "source_id",
        "supplier_source_id",
        "supplier_name",
        "product_source_id",
        "variant_source_id",
        "location_source_id",
        "quantity",
        "unit_cost",
        "currency",
        "order_date",
        "fx_rate",
    ],
    "sales": [
        "product_source_id",
        "variant_source_id",
        "customer_source_id",
        "quantity",
        "unit_price",
        "sale_date",
        "currency",
        "channel",
        "payment_method",
        "location_name",
    ],
}


def build_entity_template_csv(entity: str) -> str:
    columns = _TEMPLATE_COLUMNS[entity]
    buf = io.StringIO()
    writer = csv.writer(buf)
    writer.writerow(columns)
    writer.writerow(["#EXAMPLE"] + [""] * (len(columns) - 1))
    return buf.getvalue()


def build_readme() -> str:
    lines = [
        "ModishLog data import — CSV templates",
        "",
        "Import order (fill these files in this order so source_id references resolve):",
        *[f"  {i}. {e}.csv" for i, e in enumerate(IMPORTABLE_ENTITIES, start=1)],
        "",
        "Every file's `source_id` column is the value you use to reference that row",
        "from other files (e.g. sales.csv's `product_source_id` matches a `source_id`",
        "in products.csv).",
        "",
        "Accepted date formats: YYYY-MM-DD (preferred), DD/MM/YYYY, MM/DD/YYYY, DD-Mon-YYYY.",
        "Accepted payment_method values: card, cash, bank_transfer, cheque, mobile_money, other.",
        "",
        "purchase_orders.csv: unit_cost must be in USD, matching the FX-based landed-cost",
        "calculation used for every purchase order in ModishLog (not the `currency` column,",
        "which is only stored for display). Set fx_rate to the actual NGN/USD rate at the",
        "time of that purchase, or leave it blank to fall back to a fixed rate — for",
        "historical imports spanning any real length of time, a fixed rate will misstate",
        "landed cost and profit margin for every purchase made when the real rate differed.",
    ]
    return "\n".join(lines)
