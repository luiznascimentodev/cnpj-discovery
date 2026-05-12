import pytest

from discovery.errors import (
    SearchError,
    SearchRateLimitError,
    SearchTimeoutError,
    SearchUnavailableError,
)


class TestSearchErrors:
    def test_rate_limit_error_stores_source_and_retry_after(self):
        exc = SearchRateLimitError("brave", retry_after=900)
        assert exc.source == "brave"
        assert exc.retry_after == 900
        assert isinstance(exc, SearchError)

    def test_rate_limit_error_default_retry_after(self):
        exc = SearchRateLimitError("searxng")
        assert exc.retry_after == 60

    def test_timeout_error_stores_source(self):
        exc = SearchTimeoutError("google_cse")
        assert exc.source == "google_cse"
        assert isinstance(exc, SearchError)

    def test_unavailable_error_stores_source_and_status(self):
        exc = SearchUnavailableError("brave", status_code=503)
        assert exc.source == "brave"
        assert exc.status_code == 503
        assert isinstance(exc, SearchError)

    def test_unavailable_error_default_status_code(self):
        exc = SearchUnavailableError("google_cse")
        assert exc.status_code == 0

    def test_all_are_exceptions(self):
        for cls in (SearchRateLimitError, SearchTimeoutError, SearchUnavailableError):
            assert issubclass(cls, Exception)

    def test_messages_contain_source(self):
        assert "brave" in str(SearchRateLimitError("brave"))
        assert "searxng" in str(SearchTimeoutError("searxng"))
        assert "google_cse" in str(SearchUnavailableError("google_cse", 429))
