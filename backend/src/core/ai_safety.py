"""AI safety utilities shared across all domains.

IMPORTANT: Call contains_pii_check(prompt) before EVERY Anthropic API call.
Any future LLM integration MUST import and invoke this guard from this module.
"""

import re

# E6 — PII detection pattern (email, phone, name-like field=value text)
_PII_PATTERN = re.compile(
    r"[a-zA-Z0-9._%+\-]+@[a-zA-Z0-9.\-]+\.[a-zA-Z]{2,}"  # email
    r"|(?:\+?234|0)[789]\d{9}"  # Nigerian phone
    r"|\b(?:full_name|phone_number|email_address|nin)\s*[:=]\s*\S+",  # field=value
    re.IGNORECASE,
)

__all__ = ["contains_pii_check"]


def contains_pii_check(prompt: str) -> None:
    """Raise ValueError if PII patterns are detected in a prompt string.

    E6 — GUARD: Call this before every Anthropic API call.

    Example usage::

        from src.core.ai_safety import contains_pii_check

        # IMPORTANT: call contains_pii_check(prompt) before every anthropic client call
        contains_pii_check(user_prompt)
        response = anthropic_client.messages.create(...)

    Raises:
        ValueError: If PII is detected, with position and redacted snippet.
    """
    match = _PII_PATTERN.search(prompt)
    if match:
        raise ValueError(
            f"PII detected in prompt at position {match.start()}: "
            f"'{match.group()[:20]}...'. Remove PII before sending to external API."
        )
