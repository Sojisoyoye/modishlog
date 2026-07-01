"""Unit tests for pure helper functions in scripts/pos_migrate.py.

These tests exercise the stateless helpers only — no DB connection,
no network access, and no external service mocks are required.
"""

import os
import sys
from datetime import date
from decimal import Decimal

import pytest

# Allow importing scripts.pos_migrate without installing the package.
# The script itself inserts backend/ into sys.path; we add scripts/ here
# so that `from scripts.pos_migrate import ...` resolves correctly.
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "scripts"))

# Guard: import only the pure helpers, not the DB/network-heavy module-level
# side-effects.  The script guards its entry-point with `if __name__ == "__main__"`
# so a plain import is safe as long as the env vars for DB/POS are not set to
# live values (they default to Docker-internal addresses which won't be reachable
# in unit-test runs — that is fine because no network calls are made by the
# helpers under test).
from pos_migrate import (  # type: ignore[import]
    _infer_category,
    _parse_date,
    _parse_price,
    _parse_qty,
    _slugify,
    _strip_html,
    _unique_slug,
)


# ── _strip_html ───────────────────────────────────────────────────────────────


class TestStripHtml:
    @pytest.mark.parametrize(
        "html,expected",
        [
            # Happy path: tags removed, text returned
            ("<b>Hello</b>", "Hello"),
            ('<span class="price">₦1,500</span>', "₦1,500"),
            # No tags at all: input passes through (stripped of whitespace)
            ("Plain text", "Plain text"),
            # Leading/trailing whitespace is stripped
            ("  trimmed  ", "trimmed"),
            # Nested tags
            ("<div><p>Nested</p></div>", "Nested"),
            # Empty string
            ("", ""),
            # Self-closing tag
            ("Price<br/>here", "Pricehere"),
        ],
    )
    def test_strip_html(self, html: str, expected: str) -> None:
        assert _strip_html(html) == expected

    def test_strips_html_with_attributes(self) -> None:
        raw = '<a href="http://example.com" data-x="1">Click</a>'
        assert _strip_html(raw) == "Click"


# ── _parse_price ──────────────────────────────────────────────────────────────


class TestParsePrice:
    @pytest.mark.parametrize(
        "raw,expected",
        [
            # Happy path: plain numeric string
            ("1500", Decimal("1500")),
            # Currency symbol and commas stripped
            ("₦1,500.50", Decimal("1500.50")),
            # HTML wrapper
            ("<b>2000.00</b>", Decimal("2000.00")),
            # Zero string
            ("0", Decimal("0")),
            # Empty string → zero
            ("", Decimal("0")),
            # Non-numeric → zero
            ("N/A", Decimal("0")),
            # Decimal already correct
            ("999.99", Decimal("999.99")),
        ],
    )
    def test_parse_price(self, raw: str, expected: Decimal) -> None:
        result = _parse_price(raw)
        assert result == expected
        assert isinstance(result, Decimal)

    def test_result_is_decimal_not_float(self) -> None:
        """Financial values must be Decimal, never float."""
        result = _parse_price("1234.56")
        assert type(result) is Decimal


# ── _parse_qty ────────────────────────────────────────────────────────────────


class TestParseQty:
    @pytest.mark.parametrize(
        "raw,expected",
        [
            # Happy path: integer string
            ("10", 10),
            # Decimal quantity truncated to int
            ("3.7", 3),
            # Zero
            ("0", 0),
            # Quantity with trailing unit text
            ("25 sheets", 25),
            # Empty / non-numeric → 0
            ("", 0),
            ("N/A", 0),
            # Integer passthrough (function calls str() internally)
            (42, 42),
        ],
    )
    def test_parse_qty(self, raw, expected: int) -> None:
        result = _parse_qty(raw)
        assert result == expected
        assert isinstance(result, int)


# ── _slugify ──────────────────────────────────────────────────────────────────


class TestSlugify:
    @pytest.mark.parametrize(
        "name,expected",
        [
            # Happy path
            ("MDF Board 18mm", "mdf-board-18mm"),
            # Multiple spaces collapse to one hyphen
            ("Edge  Tape  21mm", "edge-tape-21mm"),
            # Special characters removed
            ("PU Stone (Wall)", "pu-stone-wall"),
            # Underscore treated as separator
            ("marine_board", "marine-board"),
            # Already lowercase, no change
            ("doors", "doors"),
            # Leading/trailing hyphens stripped
            ("-test-", "test"),
        ],
    )
    def test_slugify(self, name: str, expected: str) -> None:
        assert _slugify(name) == expected

    def test_slug_is_lowercase(self) -> None:
        assert _slugify("HDF UV GLOSS").islower()

    def test_slug_no_spaces(self) -> None:
        slug = _slugify("Block Board 12mm")
        assert " " not in slug


# ── _unique_slug ──────────────────────────────────────────────────────────────


class TestUniqueSlug:
    def test_returns_base_slug_when_not_in_existing(self) -> None:
        result = _unique_slug("MDF Board", set())
        assert result == "mdf-board"

    def test_appends_counter_when_slug_exists(self) -> None:
        existing = {"mdf-board"}
        result = _unique_slug("MDF Board", existing)
        assert result == "mdf-board-2"

    def test_increments_counter_past_existing_suffixes(self) -> None:
        existing = {"mdf-board", "mdf-board-2", "mdf-board-3"}
        result = _unique_slug("MDF Board", existing)
        assert result == "mdf-board-4"

    def test_does_not_mutate_existing_set(self) -> None:
        existing = {"doors"}
        _unique_slug("Doors", existing)
        # The helper must NOT add the new slug to the caller's set
        assert existing == {"doors"}

    def test_empty_existing_set(self) -> None:
        assert _unique_slug("Marine Board", set()) == "marine-board"


# ── _infer_category ───────────────────────────────────────────────────────────


class TestInferCategory:
    @pytest.mark.parametrize(
        "name,pos_category,expected",
        [
            # Block Boards: name ends with "BB"
            ("Plywood 18mm BB", "", "Block Boards"),
            # Block Boards: " BB " in middle of name (real POS format: "Brown Masonia BB Board")
            ("Customer Code BB Board", "", "Block Boards"),
            # UV Gloss: MDF UV pattern
            ("MDF UV Gloss 18mm", "", "UV Gloss Boards"),
            ("HDF UV Super 12mm", "Boards", "UV Gloss Boards"),
            # Edge Tapes: from POS category
            ("Some Product", "EDGE TAPE", "Edge Tapes"),
            # Edge Tapes: numeric mm in name
            ("Tape 21mm", "", "Edge Tapes"),
            # Marine Boards (real POS names don't include mm dimensions)
            ("Marine Plywood Sheet", "", "Marine Boards"),
            # HDF Boards (not UV)
            ("HDF Board Plain", "", "HDF Boards"),
            # MDF Boards (not UV)
            ("MDF Plain Sheet", "", "MDF Boards"),
            # Doors
            ("Flush Door 90x210", "", "Doors"),
            # PU Stone Panels
            ("PU Stone Panel White", "", "PU Stone Panels"),
            # Fallback: Accessories
            ("Random Hardware Item", "Other", "Accessories"),
        ],
    )
    def test_infer_category(self, name: str, pos_category: str, expected: str) -> None:
        assert _infer_category(name, pos_category) == expected

    def test_category_inference_is_case_insensitive_for_name(self) -> None:
        """The function uppercases internally, so mixed case should still match."""
        assert _infer_category("mdf uv gloss 18mm", "") == "UV Gloss Boards"
        assert _infer_category("marine board", "") == "Marine Boards"


# ── _parse_date ───────────────────────────────────────────────────────────────


class TestParseDate:
    @pytest.mark.parametrize(
        "raw,expected",
        [
            # ISO date with time
            ("2024-03-15 10:30:00", date(2024, 3, 15)),
            # ISO date only
            ("2024-01-01", date(2024, 1, 1)),
            # POS DD-MM-YYYY with time
            ("25-12-2023 09:00", date(2023, 12, 25)),
            # POS DD-MM-YYYY without time
            ("01-06-2024", date(2024, 6, 1)),
        ],
    )
    def test_parse_date_valid(self, raw: str, expected: date) -> None:
        result = _parse_date(raw)
        assert result == expected
        assert isinstance(result, date)

    @pytest.mark.parametrize(
        "raw",
        [
            # Completely invalid
            "not-a-date",
            # Empty string
            "",
            # Gibberish
            "??/??/????",
        ],
    )
    def test_parse_date_invalid_returns_none(self, raw: str) -> None:
        assert _parse_date(raw) is None

    def test_parse_date_returns_date_not_datetime(self) -> None:
        result = _parse_date("2024-06-15 12:00:00")
        # Must be a plain date, not a datetime
        assert type(result) is date
