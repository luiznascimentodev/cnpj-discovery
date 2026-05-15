"""
N+1 Query Detector Middleware (pure ASGI).

Conta quantas queries SQL são executadas por request HTTP e emite warnings
quando o número excede o threshold. O contador é mantido por InstrumentedConnection
(database.py) via contextvar — funciona automaticamente em produção.

Threshold padrão = 3 porque o endpoint /status dispara 3 queries legitimamente
(duas em pg_class + uma em etl_state). Todos os outros endpoints devem usar 1 query.
"""
from typing import Awaitable, Callable

from loguru import logger

from core.db import query_count

_N1_THRESHOLD = 3

Scope = dict
Receive = Callable[[], Awaitable[dict]]
Send = Callable[[dict], Awaitable[None]]


class N1DetectorMiddleware:
    def __init__(self, app) -> None:
        self._app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self._app(scope, receive, send)
            return

        query_count.set(0)
        await self._app(scope, receive, send)

        count = query_count.get()
        path = scope.get("path", "")
        method = scope.get("method", "")

        if count > _N1_THRESHOLD:
            logger.warning(
                f"[N+1 DETECTOR] {method} {path} executou {count} queries "
                f"(limite={_N1_THRESHOLD}) — verifique se há padrão N+1"
            )
        elif count > 0:
            logger.debug(f"[DB] {method} {path}: {count} quer{'y' if count == 1 else 'ies'}")
