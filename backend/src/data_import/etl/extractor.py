"""Extract layer — turns uploaded CSV files or a live source-system API into
raw, entity-keyed rows of strings. No type coercion happens here; that's the
transformer's job.
"""

import csv
import io
import re
from abc import ABC, abstractmethod
from datetime import date, datetime
from decimal import Decimal, InvalidOperation

import structlog

logger = structlog.get_logger()

ExtractedData = dict[str, list[dict[str, str]]]

# Tried in order; the first format that parses cleanly wins.
_DATE_FORMATS = [
    "%Y-%m-%d",  # ISO 8601
    "%Y-%m-%dT%H:%M:%S",
    "%d/%m/%Y",
    "%m/%d/%Y",
    "%d-%b-%y",  # 01-Jul-26
    "%d-%b-%Y",
    "%d-%m-%Y",
]

_CURRENCY_SYMBOLS = "₦$£€"


class BaseExtractor(ABC):
    """Both extraction modes (CSV upload, live API pull) satisfy this contract."""

    @abstractmethod
    async def extract(self) -> ExtractedData:
        """Return raw string rows per entity, ready for the transformer."""
        raise NotImplementedError


class CSVExtractor(BaseExtractor):
    """Reads from CSV files uploaded by the user, one file per entity."""

    def __init__(self, files: dict[str, bytes]) -> None:
        self._files = files

    async def extract(self) -> ExtractedData:
        result: ExtractedData = {}
        for entity, raw_bytes in self._files.items():
            result[entity] = _parse_csv_bytes(raw_bytes)
        return result


class APIExtractor(BaseExtractor):
    """Pulls live data from a source-system API.

    Credentials are accepted only in ``__init__`` for the lifetime of a single
    extraction call — never written to the database, never logged. Subclasses
    (one per source system) implement ``extract()``.
    """

    def __init__(self, base_url: str, credentials: dict[str, str]) -> None:
        self._base_url = base_url
        self._credentials = credentials

    @abstractmethod
    async def extract(self) -> ExtractedData:
        raise NotImplementedError

    @abstractmethod
    async def test_connection(self) -> dict:
        """Authenticate and return row counts + date range without a full pull."""
        raise NotImplementedError


def _parse_csv_bytes(raw_bytes: bytes) -> list[dict[str, str]]:
    text = _decode_bytes(raw_bytes)
    reader = csv.DictReader(io.StringIO(text))
    return [
        {k: (v.strip() if isinstance(v, str) else v) for k, v in row.items() if k is not None}
        for row in reader
    ]


def _decode_bytes(raw_bytes: bytes) -> str:
    """Handle BOM'd UTF-8 first, fall back to Latin-1 for legacy exports."""
    try:
        return raw_bytes.decode("utf-8-sig")
    except UnicodeDecodeError:
        return raw_bytes.decode("latin-1")


def parse_flexible_date(value: str) -> date:
    """Try ISO 8601 first, then common regional formats."""
    value = value.strip()
    for fmt in _DATE_FORMATS:
        try:
            return datetime.strptime(value, fmt).date()
        except ValueError:
            continue
    raise ValueError(f"Unrecognised date format: {value!r}")


def parse_flexible_amount(value: str) -> Decimal:
    """Strip currency symbols and normalise US (1,200.00) vs European (1.200,00)
    thousands/decimal separators into a Decimal.
    """
    cleaned = value.strip()
    for symbol in _CURRENCY_SYMBOLS:
        cleaned = cleaned.replace(symbol, "")
    cleaned = cleaned.strip()

    if "," in cleaned and "." in cleaned:
        if cleaned.rfind(",") > cleaned.rfind("."):
            # European: comma is the decimal separator, dot is thousands.
            cleaned = cleaned.replace(".", "").replace(",", ".")
        else:
            # US: comma is thousands, dot is decimal.
            cleaned = cleaned.replace(",", "")
    elif "," in cleaned:
        # Only a comma present — decide by digit count after it.
        tail = cleaned.rsplit(",", 1)[1]
        cleaned = cleaned.replace(",", "." if len(tail) in (1, 2) else "")

    cleaned = re.sub(r"[^\d.\-]", "", cleaned)
    if not cleaned:
        raise InvalidOperation(f"Not a numeric amount: {value!r}")
    return Decimal(cleaned)


def detect_source_system(headers: set[str]) -> str | None:
    """Best-effort guess at the originating system from a CSV's column headers."""
    if {"variation_id", "sell_price_inc_tax"} & headers:
        return "ultimatepos"
    if {"Option1 Name", "Option1 Value", "Variant SKU"} & headers:
        return "shopify"
    if {"QuickBooks Internal ID", "Item(Product/Service)"} & headers:
        return "quickbooks"
    return None
