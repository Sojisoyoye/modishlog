"""Shared utilities for the products domain."""

import re


def slugify(name: str) -> str:
    """Generate a URL-safe slug from a product name.

    Rules (matches the modish-standard sync script):
    - Lowercase
    - Spaces → hyphens
    - Special chars stripped (except hyphens)
    - Multiple hyphens collapsed
    - Leading/trailing hyphens removed
    - "×" (U+00D7) and "*" treated as "x" before stripping (e.g. "0.5×48" → "05x48")
    """
    s = name.replace("×", "x").replace("*", "x")
    s = s.lower()
    s = s.replace(" ", "-")
    s = re.sub(r"[^a-z0-9\-]", "", s)
    s = re.sub(r"-+", "-", s)
    return s.strip("-")
