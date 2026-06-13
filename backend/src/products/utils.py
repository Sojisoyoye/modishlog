"""Shared utilities for the products domain."""

import re
import unicodedata


def slugify(name: str) -> str:
    """Generate a URL-safe slug from a product name.

    Rules (matches the modish-standard sync script):
    - Lowercase
    - Spaces → hyphens
    - Special chars stripped (except hyphens)
    - Multiple hyphens collapsed
    - Leading/trailing hyphens removed
    - "×" (U+00D7) and "*" treated as "x" before stripping (e.g. "0.5×48" → "05x48")
    - Accented/unicode letters transliterated to ASCII via NFKD (e.g. "café" → "cafe")

    Returns an empty string if the name contains no alphanumeric characters after
    normalisation. Callers are responsible for rejecting empty slugs.
    """
    s = name.replace("×", "x").replace("*", "x")
    s = unicodedata.normalize("NFKD", s).encode("ascii", "ignore").decode("ascii")
    s = s.lower()
    s = s.replace(" ", "-")
    s = re.sub(r"[^a-z0-9\-]", "", s)
    s = re.sub(r"-+", "-", s)
    return s.strip("-")
