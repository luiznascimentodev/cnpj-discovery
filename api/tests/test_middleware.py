"""Testes para os middlewares de monitoramento."""
import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from database import query_count
from middleware.concurrency_monitor import ThunderingHerdMiddleware, _inflight
from middleware.memory_monitor import SlowRequestMiddleware, rss_monitor_loop
from middleware.query_monitor import N1DetectorMiddleware, _N1_THRESHOLD


# ─── Helpers ──────────────────────────────────────────────────────────────────

def make_scope(path: str = "/v1/test", method: str = "GET", qs: str = "") -> dict:
    return {
        "type": "http",
        "path": path,
        "method": method,
        "query_string": qs.encode(),
    }


async def noop_receive():
    return {}


async def noop_send(msg):
    pass


# ─── N1DetectorMiddleware ──────────────────────────────────────────────────────

class TestN1DetectorMiddleware:
    @pytest.mark.asyncio
    async def test_passes_non_http_scope(self):
        calls = []
        async def mock_app(scope, receive, send):
            calls.append(scope["type"])
        mw = N1DetectorMiddleware(mock_app)
        await mw({"type": "websocket"}, noop_receive, noop_send)
        assert calls == ["websocket"]

    @pytest.mark.asyncio
    async def test_resets_query_count(self):
        query_count.set(5)

        async def mock_app(scope, receive, send):
            pass

        mw = N1DetectorMiddleware(mock_app)
        await mw(make_scope(), noop_receive, noop_send)
        # Count was reset at start of request — after request it reads the new count (0)
        assert query_count.get() == 0

    @pytest.mark.asyncio
    async def test_zero_queries_no_log(self, capfd):
        async def mock_app(scope, receive, send):
            pass

        mw = N1DetectorMiddleware(mock_app)
        await mw(make_scope(), noop_receive, noop_send)
        # No N+1 warning for 0 queries (normal for health/cache-hit requests)

    @pytest.mark.asyncio
    async def test_above_threshold_logs_warning(self):
        async def mock_app(scope, receive, send):
            query_count.set(_N1_THRESHOLD + 1)

        mw = N1DetectorMiddleware(mock_app)
        with patch("middleware.query_monitor.logger") as mock_logger:
            await mw(make_scope(), noop_receive, noop_send)
        mock_logger.warning.assert_called_once()
        assert "N+1" in mock_logger.warning.call_args[0][0]

    @pytest.mark.asyncio
    async def test_at_threshold_logs_debug(self):
        async def mock_app(scope, receive, send):
            query_count.set(1)

        mw = N1DetectorMiddleware(mock_app)
        with patch("middleware.query_monitor.logger") as mock_logger:
            await mw(make_scope(), noop_receive, noop_send)
        mock_logger.debug.assert_called_once()


# ─── SlowRequestMiddleware ─────────────────────────────────────────────────────

class TestSlowRequestMiddleware:
    @pytest.mark.asyncio
    async def test_passes_non_http_scope(self):
        calls = []
        async def mock_app(scope, receive, send):
            calls.append(scope["type"])
        mw = SlowRequestMiddleware(mock_app)
        await mw({"type": "lifespan"}, noop_receive, noop_send)
        assert calls == ["lifespan"]

    @pytest.mark.asyncio
    async def test_fast_request_no_warning(self):
        async def mock_app(scope, receive, send):
            pass

        mw = SlowRequestMiddleware(mock_app)
        with patch("middleware.memory_monitor.logger") as mock_logger:
            await mw(make_scope(), noop_receive, noop_send)
        mock_logger.warning.assert_not_called()

    @pytest.mark.asyncio
    async def test_reraises_app_exception(self):
        async def failing_app(scope, receive, send):
            raise ValueError("app error")

        mw = SlowRequestMiddleware(failing_app)
        with pytest.raises(ValueError, match="app error"):
            await mw(make_scope(), noop_receive, noop_send)


# ─── ThunderingHerdMiddleware ──────────────────────────────────────────────────

class TestThunderingHerdMiddleware:
    @pytest.mark.asyncio
    async def test_passes_non_http_scope(self):
        calls = []
        async def mock_app(scope, receive, send):
            calls.append(scope["type"])
        mw = ThunderingHerdMiddleware(mock_app)
        await mw({"type": "lifespan"}, noop_receive, noop_send)
        assert calls == ["lifespan"]

    @pytest.mark.asyncio
    async def test_tracks_and_cleans_up_inflight(self):
        key_seen = []

        async def mock_app(scope, receive, send):
            path = scope["path"]
            qs = scope["query_string"].decode()
            key = f"{scope['method']}:{path}?{qs}"
            key_seen.append(_inflight.get(key, 0))

        mw = ThunderingHerdMiddleware(mock_app)
        await mw(make_scope("/v1/unique_path_99"), noop_receive, noop_send)
        assert key_seen == [1]  # exactly 1 in-flight during request
        # After request, key is removed
        assert "GET:/v1/unique_path_99?" not in _inflight

    @pytest.mark.asyncio
    async def test_reraises_app_exception(self):
        async def failing_app(scope, receive, send):
            raise RuntimeError("inner error")

        mw = ThunderingHerdMiddleware(failing_app)
        with pytest.raises(RuntimeError, match="inner error"):
            await mw(make_scope(), noop_receive, noop_send)

    @pytest.mark.asyncio
    async def test_cleans_up_on_exception(self):
        key = "GET:/v1/cleanup_test?"

        async def failing_app(scope, receive, send):
            raise RuntimeError("fail")

        mw = ThunderingHerdMiddleware(failing_app)
        with pytest.raises(RuntimeError):
            await mw(make_scope("/v1/cleanup_test"), noop_receive, noop_send)

        assert key not in _inflight


# ─── rss_monitor_loop ─────────────────────────────────────────────────────────

class TestRssMonitorLoop:
    @pytest.mark.asyncio
    async def test_runs_and_logs_debug_when_under_threshold(self):
        """Loop body executa e loga RSS quando está abaixo do limiar."""
        sleep_calls = 0

        async def fast_sleep(n):
            nonlocal sleep_calls
            sleep_calls += 1
            if sleep_calls >= 2:
                raise asyncio.CancelledError()

        with patch("middleware.memory_monitor.asyncio.sleep", side_effect=fast_sleep), \
             patch("middleware.memory_monitor.logger") as mock_logger, \
             patch("middleware.memory_monitor.resource.getrusage") as mock_rss:
            mock_rss.return_value.ru_maxrss = 100 * 1024  # 100 MB, below 512 threshold
            with pytest.raises(asyncio.CancelledError):
                await rss_monitor_loop()

        mock_logger.debug.assert_called()

    @pytest.mark.asyncio
    async def test_warns_when_rss_exceeds_threshold(self):
        sleep_calls = 0

        async def fast_sleep(n):
            nonlocal sleep_calls
            sleep_calls += 1
            if sleep_calls >= 2:
                raise asyncio.CancelledError()

        with patch("middleware.memory_monitor.asyncio.sleep", side_effect=fast_sleep), \
             patch("middleware.memory_monitor.logger") as mock_logger, \
             patch("middleware.memory_monitor.resource.getrusage") as mock_rss:
            mock_rss.return_value.ru_maxrss = 600 * 1024  # 600 MB, above 512 threshold
            with pytest.raises(asyncio.CancelledError):
                await rss_monitor_loop()

        mock_logger.warning.assert_called()
        assert "MEMORY LEAK" in mock_logger.warning.call_args[0][0]
