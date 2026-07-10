"""Tests for wiring live-API extraction into the data_import job lifecycle.

Task 162 Phase 0 shipped 6 vendor adapters implementing `APIExtractor` but
left `service.py` unconditionally raising NotImplementedError for any
API-mode job. These tests cover the actual wiring: extraction happens once
at job-creation time (credentials are used only then, never persisted), the
resulting rows get cached to disk, and validate/confirm/snapshot re-read
that cache without needing credentials again.
"""

import json
import os
import uuid
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi.testclient import TestClient

from src.data_import.etl.extractor import APIExtractor
from src.data_import.exceptions import UnsupportedSourceSystemError
from src.data_import.models import ExtractionMode, MigrationJob, MigrationJobStatus, SourceSystem
from src.data_import.service import _extract_and_transform, create_job

BUSINESS_ID = uuid.uuid4()
CREATED_BY = uuid.uuid4()


class _FakeAPIExtractor(APIExtractor):
    def __init__(self, base_url, credentials, rows=None, error=None):
        super().__init__(base_url, credentials)
        self._rows = rows if rows is not None else {
            "products": [
                {"source_id": "P1", "name": "Widget", "unit_cost": "5", "selling_price": "10"}
            ]
        }
        self._error = error

    async def extract(self):
        if self._error:
            raise self._error
        return self._rows

    async def test_connection(self):
        return {"counts": {}, "date_range": None}


def _populate_defaults(obj) -> None:
    """A real flush() would populate SQLAlchemy column defaults (id,
    created_at, ...) — the mocked session doesn't, so router-level tests that
    serialize the object via a Pydantic response model need this simulated."""
    from datetime import datetime, timezone

    if getattr(obj, "id", None) is None:
        obj.id = uuid.uuid4()
    if getattr(obj, "created_at", None) is None:
        obj.created_at = datetime.now(timezone.utc)
    if getattr(obj, "updated_at", None) is None:
        obj.updated_at = datetime.now(timezone.utc)
    if getattr(obj, "validation_errors", None) is None:
        obj.validation_errors = []
    if getattr(obj, "validation_warnings", None) is None:
        obj.validation_warnings = []
    if getattr(obj, "row_counts", None) is None:
        obj.row_counts = {}


def _mock_db():
    db = AsyncMock()
    db.flush = AsyncMock()
    db.add = MagicMock(side_effect=_populate_defaults)
    return db


def _none_result():
    r = MagicMock()
    r.scalar_one_or_none.return_value = None
    return r


def _make_job(**overrides) -> MigrationJob:
    defaults = dict(
        business_id=BUSINESS_ID,
        status=MigrationJobStatus.PENDING,
        source_system=SourceSystem.ULTIMATEPOS,
        extraction_mode=ExtractionMode.API,
        created_by=CREATED_BY,
        api_base_url="https://pos.example.com",
    )
    defaults.update(overrides)
    job = MigrationJob(**defaults)
    job.id = overrides.get("id", uuid.uuid4())
    return job


class TestCreateJobApiMode:
    @pytest.mark.asyncio
    async def test_extracts_and_caches_rows_immediately(self, tmp_path, monkeypatch):
        monkeypatch.setattr("src.data_import.service.settings.UPLOAD_DIR", str(tmp_path))
        db = _mock_db()

        with patch.dict(
            "src.data_import.service.API_ADAPTERS", {"ultimatepos": _FakeAPIExtractor}
        ):
            job = await create_job(
                db,
                business_id=BUSINESS_ID,
                user_id=CREATED_BY,
                source_system=SourceSystem.ULTIMATEPOS,
                extraction_mode=ExtractionMode.API,
                api_base_url="https://pos.example.com",
                credentials={"username": "u", "password": "p"},
            )

        assert job.row_counts == {"products": 1}
        assert job.status == MigrationJobStatus.PENDING

        cache_path = os.path.join(str(tmp_path), "imports", str(job.id), "extracted.json")
        assert os.path.isfile(cache_path)
        with open(cache_path) as f:
            cached = json.load(f)
        assert cached["products"][0]["source_id"] == "P1"

    @pytest.mark.asyncio
    async def test_extraction_failure_marks_job_failed_and_raises(self, tmp_path, monkeypatch):
        monkeypatch.setattr("src.data_import.service.settings.UPLOAD_DIR", str(tmp_path))
        db = _mock_db()

        def _bad_adapter(base_url, credentials):
            return _FakeAPIExtractor(base_url, credentials, error=ConnectionError("bad creds"))

        with patch.dict("src.data_import.service.API_ADAPTERS", {"ultimatepos": _bad_adapter}):
            with pytest.raises(ConnectionError):
                await create_job(
                    db,
                    business_id=BUSINESS_ID,
                    user_id=CREATED_BY,
                    source_system=SourceSystem.ULTIMATEPOS,
                    extraction_mode=ExtractionMode.API,
                    api_base_url="https://pos.example.com",
                    credentials={"username": "u"},
                )

        added_job = db.add.call_args_list[0].args[0]
        assert added_job.status == MigrationJobStatus.FAILED

    @pytest.mark.asyncio
    async def test_unsupported_source_system_raises(self, tmp_path, monkeypatch):
        monkeypatch.setattr("src.data_import.service.settings.UPLOAD_DIR", str(tmp_path))
        db = _mock_db()

        with patch.dict("src.data_import.service.API_ADAPTERS", {}, clear=True):
            with pytest.raises(UnsupportedSourceSystemError):
                await create_job(
                    db,
                    business_id=BUSINESS_ID,
                    user_id=CREATED_BY,
                    source_system=SourceSystem.ULTIMATEPOS,
                    extraction_mode=ExtractionMode.API,
                    api_base_url="https://x.example.com",
                    credentials={},
                )

    @pytest.mark.asyncio
    async def test_csv_mode_never_touches_api_adapters(self, tmp_path, monkeypatch):
        """Regression guard: CSV-mode job creation must not attempt extraction."""
        monkeypatch.setattr("src.data_import.service.settings.UPLOAD_DIR", str(tmp_path))
        db = _mock_db()

        job = await create_job(
            db,
            business_id=BUSINESS_ID,
            user_id=CREATED_BY,
            source_system=SourceSystem.GENERIC,
            extraction_mode=ExtractionMode.CSV,
            files={"products": b"source_id,name\nP1,Widget\n"},
        )
        # CSV mode never sets row_counts at creation time (only validate_job
        # does) — it stays at the empty default, confirming create_job's
        # API-mode branch (which explicitly sets *real* counts) never ran.
        assert job.row_counts == {}
        assert job.status == MigrationJobStatus.PENDING


class TestExtractAndTransformApiMode:
    @pytest.mark.asyncio
    async def test_reads_cached_extraction_without_credentials(self, tmp_path, monkeypatch):
        monkeypatch.setattr("src.data_import.service.settings.UPLOAD_DIR", str(tmp_path))
        job = _make_job()
        cache_dir = os.path.join(str(tmp_path), "imports", str(job.id))
        os.makedirs(cache_dir, exist_ok=True)
        with open(os.path.join(cache_dir, "extracted.json"), "w") as f:
            json.dump(
                {
                    "products": [
                        {"source_id": "P1", "name": "Widget", "unit_cost": "5", "selling_price": "10"}
                    ]
                },
                f,
            )

        db = _mock_db()
        db.execute = AsyncMock(return_value=_none_result())

        mapped, transformed, transformer = await _extract_and_transform(db, job)

        assert mapped["products"][0]["source_id"] == "P1"
        assert len(transformed["products"]) == 1
        assert transformed["products"][0]["name"] == "Widget"

    @pytest.mark.asyncio
    async def test_missing_cache_produces_empty_result_not_a_crash(self, tmp_path, monkeypatch):
        """No cached extraction on disk (e.g. job created before this feature
        existed) degrades to an empty import rather than raising."""
        monkeypatch.setattr("src.data_import.service.settings.UPLOAD_DIR", str(tmp_path))
        job = _make_job(id=uuid.uuid4())

        db = _mock_db()
        db.execute = AsyncMock(return_value=_none_result())

        mapped, transformed, _transformer = await _extract_and_transform(db, job)

        assert mapped == {}
        assert all(len(rows) == 0 for rows in transformed.values())


class TestCreateJobEndpointApiMode:
    @pytest.fixture(autouse=True)
    def _setup(self, tmp_path, monkeypatch):
        from src.main import app

        monkeypatch.setattr("src.data_import.service.settings.UPLOAD_DIR", str(tmp_path))
        self.app = app
        self._orig = app.dependency_overrides.copy()
        yield
        app.dependency_overrides = self._orig

    def _override(self, db):
        from src.auth.dependencies import get_current_active_user, get_current_business_id
        from src.auth.models import User
        from src.core.database import get_db

        async def _fake_db():
            yield db

        user = MagicMock(spec=User)
        user.id = CREATED_BY

        self.app.dependency_overrides[get_db] = _fake_db
        self.app.dependency_overrides[get_current_active_user] = lambda: user
        self.app.dependency_overrides[get_current_business_id] = lambda: BUSINESS_ID

    def test_credentials_reach_the_adapter_and_never_appear_in_the_response(self):
        db = _mock_db()
        self._override(db)

        with patch.dict(
            "src.data_import.service.API_ADAPTERS", {"ultimatepos": _FakeAPIExtractor}
        ):
            with TestClient(self.app) as client:
                resp = client.post(
                    "/api/v1/import/jobs",
                    data={
                        "source_system": "ultimatepos",
                        "extraction_mode": "api",
                        "api_base_url": "https://pos.example.com",
                        "username": "admin",
                        "password": "hunter2",
                    },
                )

        assert resp.status_code == 201
        body = resp.json()
        assert body["row_counts"] == {"products": 1}
        assert "password" not in json.dumps(body)
        assert "hunter2" not in json.dumps(body)

    def test_unsupported_source_system_returns_400(self):
        db = _mock_db()
        self._override(db)

        with patch.dict("src.data_import.service.API_ADAPTERS", {}, clear=True):
            with TestClient(self.app) as client:
                resp = client.post(
                    "/api/v1/import/jobs",
                    data={
                        "source_system": "ultimatepos",
                        "extraction_mode": "api",
                        "api_base_url": "https://pos.example.com",
                    },
                )

        assert resp.status_code == 400
