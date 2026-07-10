import uuid
import zipfile
from io import BytesIO

import structlog
from fastapi import APIRouter, Depends, File, Form, HTTPException, Response, UploadFile, status
from sqlalchemy.ext.asyncio import AsyncSession

from src.auth.dependencies import get_current_active_user, get_current_business_id
from src.auth.models import User
from src.core.database import get_db
from src.data_import import service
from src.data_import.etl.adapters.registry import API_ADAPTERS
from src.data_import.etl.extractor import APIExtractor
from src.data_import.exceptions import (
    InvalidJobStateError,
    MigrationJobNotFoundError,
    MissingExtractedDataError,
    UnsupportedSourceSystemError,
)
from src.data_import.models import ExtractionMode, SourceSystem
from src.data_import.schemas import (
    ConfirmationSnapshot,
    ConfirmRequest,
    MigrationJobListResponse,
    MigrationJobRead,
    TestConnectionRequest,
    TestConnectionResponse,
)

logger = structlog.get_logger()

router = APIRouter(dependencies=[Depends(get_current_active_user)])


def _credentials_from_form(
    username: str | None, password: str | None, access_token: str | None
) -> dict[str, str]:
    return {
        k: v
        for k, v in {"username": username, "password": password, "access_token": access_token}.items()
        if v is not None
    }


# ---------------------------------------------------------------------------
# Templates — static routes BEFORE parameterized
# ---------------------------------------------------------------------------


@router.get("/templates")
async def get_all_templates():
    buf = BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        zf.writestr("README.txt", service.build_readme())
        for entity in service.IMPORTABLE_ENTITIES:
            zf.writestr(f"{entity}.csv", service.build_entity_template_csv(entity))
    return Response(
        content=buf.getvalue(),
        media_type="application/zip",
        headers={"Content-Disposition": "attachment; filename=modishlog-import-templates.zip"},
    )


@router.get("/templates/{entity}")
async def get_entity_template(entity: str):
    if entity not in service.IMPORTABLE_ENTITIES:
        raise HTTPException(status_code=404, detail=f"Unknown entity: {entity}")
    content = service.build_entity_template_csv(entity)
    return Response(
        content=content,
        media_type="text/csv",
        headers={"Content-Disposition": f"attachment; filename={entity}.csv"},
    )


@router.post("/jobs/test-connection", response_model=TestConnectionResponse)
async def test_connection(data: TestConnectionRequest):
    adapter_cls = API_ADAPTERS.get(data.source_system.value)
    if adapter_cls is None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"No live-API adapter available for {data.source_system.value}",
        )
    credentials = _credentials_from_form(data.username, data.password, data.access_token)
    extractor: APIExtractor = adapter_cls(data.api_base_url, credentials)
    try:
        result = await extractor.test_connection()
    except NotImplementedError as e:
        raise HTTPException(status_code=status.HTTP_501_NOT_IMPLEMENTED, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
    return TestConnectionResponse(connected=True, source_system=data.source_system, **result)


# ---------------------------------------------------------------------------
# Jobs
# ---------------------------------------------------------------------------


@router.post("/jobs", response_model=MigrationJobRead, status_code=status.HTTP_201_CREATED)
async def create_job(
    source_system: SourceSystem = Form(...),
    extraction_mode: ExtractionMode = Form(ExtractionMode.CSV),
    product_categories: UploadFile | None = File(None),
    products: UploadFile | None = File(None),
    product_variants: UploadFile | None = File(None),
    suppliers: UploadFile | None = File(None),
    customers: UploadFile | None = File(None),
    business_locations: UploadFile | None = File(None),
    sales: UploadFile | None = File(None),
    api_base_url: str | None = Form(None),
    username: str | None = Form(None),
    password: str | None = Form(None),
    access_token: str | None = Form(None),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
    business_id: uuid.UUID = Depends(get_current_business_id),
):
    uploads = {
        "product_categories": product_categories,
        "products": products,
        "product_variants": product_variants,
        "suppliers": suppliers,
        "customers": customers,
        "business_locations": business_locations,
        "sales": sales,
    }
    files: dict[str, bytes] = {}
    for entity, upload in uploads.items():
        if upload is not None:
            files[entity] = await upload.read()

    # API-mode only — used once for the initial pull, never persisted (see
    # service.create_job). Left out of the response model entirely.
    credentials = _credentials_from_form(username, password, access_token)

    try:
        job = await service.create_job(
            db,
            business_id=business_id,
            user_id=current_user.id,
            source_system=source_system,
            extraction_mode=extraction_mode,
            files=files,
            api_base_url=api_base_url,
            credentials=credentials or None,
        )
    except UnsupportedSourceSystemError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
    except NotImplementedError as e:
        raise HTTPException(status_code=status.HTTP_501_NOT_IMPLEMENTED, detail=str(e))
    except Exception:
        # Don't leak the raw exception to the client — it may echo request
        # context (the adapter received the credentials in this same call)
        # or internal details from the HTTP/parsing library. Log the real
        # cause server-side; the client gets a safe, generic message.
        await logger.aexception("data_import_extraction_failed", source_system=source_system.value)
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Could not extract data from the source system — check the base URL and credentials.",
        )
    return job


@router.get("/jobs", response_model=MigrationJobListResponse)
async def list_jobs(
    db: AsyncSession = Depends(get_db),
    business_id: uuid.UUID = Depends(get_current_business_id),
):
    jobs = await service.list_jobs(db, business_id=business_id)
    return MigrationJobListResponse(items=jobs)


@router.get("/jobs/{job_id}", response_model=MigrationJobRead)
async def get_job(
    job_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    business_id: uuid.UUID = Depends(get_current_business_id),
):
    try:
        return await service.get_job(db, job_id, business_id=business_id)
    except MigrationJobNotFoundError:
        raise HTTPException(status_code=404, detail="Migration job not found")


@router.post("/jobs/{job_id}/validate", response_model=MigrationJobRead)
async def validate_job(
    job_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    business_id: uuid.UUID = Depends(get_current_business_id),
):
    try:
        job = await service.get_job(db, job_id, business_id=business_id)
    except MigrationJobNotFoundError:
        raise HTTPException(status_code=404, detail="Migration job not found")
    try:
        return await service.validate_job(db, job)
    except MissingExtractedDataError as e:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e))


@router.get("/jobs/{job_id}/confirmation-snapshot", response_model=ConfirmationSnapshot)
async def confirmation_snapshot(
    job_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    business_id: uuid.UUID = Depends(get_current_business_id),
):
    try:
        job = await service.get_job(db, job_id, business_id=business_id)
    except MigrationJobNotFoundError:
        raise HTTPException(status_code=404, detail="Migration job not found")
    try:
        return await service.build_confirmation_snapshot(db, job)
    except InvalidJobStateError as e:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(e))
    except MissingExtractedDataError as e:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e))


@router.post("/jobs/{job_id}/confirm", response_model=MigrationJobRead)
async def confirm_job(
    job_id: uuid.UUID,
    data: ConfirmRequest,
    db: AsyncSession = Depends(get_db),
    business_id: uuid.UUID = Depends(get_current_business_id),
):
    try:
        job = await service.get_job(db, job_id, business_id=business_id)
    except MigrationJobNotFoundError:
        raise HTTPException(status_code=404, detail="Migration job not found")
    try:
        return await service.confirm_job(db, job, approved=data.approved)
    except InvalidJobStateError as e:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(e))
    except MissingExtractedDataError as e:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e))


@router.delete("/jobs/{job_id}", response_model=MigrationJobRead)
async def rollback_job(
    job_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    business_id: uuid.UUID = Depends(get_current_business_id),
):
    try:
        job = await service.get_job(db, job_id, business_id=business_id)
    except MigrationJobNotFoundError:
        raise HTTPException(status_code=404, detail="Migration job not found")
    try:
        return await service.rollback_job(db, job)
    except InvalidJobStateError as e:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(e))
