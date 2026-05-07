"""
Race Condition / Thundering Herd Detector (pure ASGI).

Detecta quando múltiplas requests idênticas chegam simultaneamente (thundering herd).
Isso acontece tipicamente quando o cache expira e várias corrotinas tentam recomputar
o mesmo resultado ao mesmo tempo, causando rajadas de queries idênticas no PostgreSQL.
"""
import asyncio
from collections import defaultdict
from typing import Awaitable, Callable

from loguru import logger

_THUNDERING_HERD_THRESHOLD = 5

_inflight: dict[str, int] = defaultdict(int)
_lock = asyncio.Lock()

Scope = dict
Receive = Callable[[], Awaitable[dict]]
Send = Callable[[dict], Awaitable[None]]


class ThunderingHerdMiddleware:
    def __init__(self, app) -> None:
        self._app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self._app(scope, receive, send)
            return

        path = scope.get("path", "")
        method = scope.get("method", "")
        qs = scope.get("query_string", b"").decode()
        key = f"{method}:{path}?{qs}"

        async with _lock:
            _inflight[key] += 1
            concurrent = _inflight[key]

        if concurrent >= _THUNDERING_HERD_THRESHOLD:  # pragma: no cover
            logger.warning(
                f"[RACE DETECTOR] {concurrent} requests idênticas simultâneas: {key} "
                f"— possível thundering herd (cache expirou?)"
            )

        try:
            await self._app(scope, receive, send)
        finally:
            async with _lock:
                _inflight[key] -= 1
                if _inflight[key] == 0:
                    del _inflight[key]
