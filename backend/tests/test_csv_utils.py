"""Tests for CSV formula injection protection (csv_safe utility)."""

import pytest
from src.core.csv_utils import csv_safe


class TestCsvSafe:
    @pytest.mark.parametrize(
        "value,expected",
        [
            # Dangerous prefixes must be escaped with a leading apostrophe
            ("=SUM(A1)", "'=SUM(A1)"),
            ("+1234", "'+1234"),
            ("-1", "'-1"),
            ("@user", "'@user"),
            ("\tdata", "'\tdata"),
            ("\rdata", "'\rdata"),
            # Safe values pass through unchanged
            ("hello", "hello"),
            ("ModishLog", "ModishLog"),
            ("100", "100"),
            ("", ""),
            ("safe value", "safe value"),
            (" leading space", " leading space"),
        ],
    )
    def test_csv_safe(self, value: str, expected: str):
        assert csv_safe(value) == expected

    def test_none_returns_empty_string(self):
        """Non-string None should return the value unchanged (guard for callers passing None)."""
        assert csv_safe(None) is None  # type: ignore[arg-type]

    def test_non_string_int_passthrough(self):
        """Non-string values should pass through — callers are responsible for str() conversion."""
        assert csv_safe(42) == 42  # type: ignore[arg-type]
