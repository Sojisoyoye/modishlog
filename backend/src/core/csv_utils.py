"""CSV formula-injection protection utilities."""

_INJECTION_PREFIXES = frozenset({"=", "+", "-", "@", "\t", "\r"})


def csv_safe(v: str) -> str:
    """Prefix any cell value that starts with a formula-injection character with a single quote.

    Spreadsheet applications (Excel, LibreOffice, Google Sheets) treat cells
    starting with =, +, -, @, TAB, or CR as formulas or commands.  Prepending
    an apostrophe forces the value to be treated as plain text.
    """
    if isinstance(v, str) and v and v[0] in _INJECTION_PREFIXES:
        return "'" + v
    return v
