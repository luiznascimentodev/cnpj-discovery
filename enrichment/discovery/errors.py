"""Typed errors for external search providers.

Allows callers to distinguish transient failures (timeout, 503) from
quota violations (429) that require a global source-level backoff.
"""
from __future__ import annotations


class SearchError(Exception):
    """Base class for all search provider errors."""
    source: str


class SearchRateLimitError(SearchError):
    """Provider returned 429 or a soft-block response.

    retry_after: seconds the caller should wait before using this source again.
    """

    def __init__(self, source: str, retry_after: int = 60) -> None:
        self.source = source
        self.retry_after = retry_after
        super().__init__(f"{source} rate-limited, retry after {retry_after}s")


class SearchTimeoutError(SearchError):
    """Request timed out — transient, skip this source and try the next."""

    def __init__(self, source: str) -> None:
        self.source = source
        super().__init__(f"{source} request timed out")


class SearchUnavailableError(SearchError):
    """Provider returned a non-retryable error (5xx, connect failure, bad JSON).

    Transient — skip this source and try the next.
    """

    def __init__(self, source: str, status_code: int = 0) -> None:
        self.source = source
        self.status_code = status_code
        super().__init__(f"{source} unavailable (HTTP {status_code})")
