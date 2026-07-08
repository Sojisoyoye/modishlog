"""Resilience utilities: retry, circuit breaker patterns for external API calls."""

import functools
from collections.abc import Callable
from typing import Any

import structlog
from tenacity import (
    RetryError,
    retry,
    retry_if_exception_type,
    stop_after_attempt,
    wait_exponential,
)

logger = structlog.get_logger()


def retry_with_fallback(
    max_attempts: int = 3,
    wait: float = 1.0,
    exception_types: tuple[type[Exception], ...] = (Exception,),
) -> Callable:
    """Decorator factory that retries a coroutine up to *max_attempts* times.

    Parameters
    ----------
    max_attempts:
        Maximum number of total call attempts (including the first call).
    wait:
        Base wait time in seconds between retries (exponential back-off:
        wait * 2^attempt, capped at 10s).
    exception_types:
        Tuple of exception types that trigger a retry.

    Usage::

        @retry_with_fallback(max_attempts=3, wait=1)
        async def fetch_fx_rate(url: str) -> Decimal:
            ...

    When all retries are exhausted the underlying exception is re-raised so
    the caller can apply its own fallback logic (e.g. return a stale cached rate).
    """

    def decorator(fn: Callable) -> Callable:
        # reraise=False: tenacity raises RetryError when all attempts are exhausted.
        # We catch RetryError below, log it, then re-raise the *original* exception
        # so callers receive the root cause rather than a tenacity wrapper.
        retry_decorator = retry(
            reraise=False,
            stop=stop_after_attempt(max_attempts),
            wait=wait_exponential(multiplier=wait, min=wait, max=10),
            retry=retry_if_exception_type(exception_types),
        )
        wrapped = retry_decorator(fn)

        @functools.wraps(fn)
        async def wrapper(*args: Any, **kwargs: Any) -> Any:
            try:
                return await wrapped(*args, **kwargs)
            except RetryError as exc:
                # tenacity raises RetryError after all attempts; unwrap to original cause
                original = exc.last_attempt.exception()
                logger.warning(
                    "retry_exhausted",
                    function=fn.__qualname__,
                    attempts=max_attempts,
                    error=str(original),
                )
                raise original from exc

        return wrapper

    return decorator
