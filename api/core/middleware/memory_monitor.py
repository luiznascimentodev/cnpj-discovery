"""
Memory Leak Detector (pure ASGI).

Dois mecanismos:
  1. Background task rss_monitor_loop: verifica RSS a cada intervalo e alerta
     quando ultrapassa o limiar. Vazamentos de memória aparecem como crescimento
     monótono do RSS ao longo do tempo.
  2. SlowRequestMiddleware: requests que demoram mais que _SLOW_REQUEST_WARN_S
     segundos são logadas como suspeitas de connection hold / deadlock.
"""
import asyncio
import resource
import time
from typing import Awaitable, Callable

from loguru import logger

_RSS_WARN_MB = 512.0
_RSS_CHECK_INTERVAL_S = 60
_SLOW_REQUEST_WARN_S = 30.0

Scope = dict
Receive = Callable[[], Awaitable[dict]]
Send = Callable[[dict], Awaitable[None]]


async def rss_monitor_loop() -> None:
    """Executa em background; loga RSS e alerta quando ultrapassa o limiar."""
    while True:
        await asyncio.sleep(_RSS_CHECK_INTERVAL_S)
        try:
            usage = resource.getrusage(resource.RUSAGE_SELF)
            rss_mb = usage.ru_maxrss / 1024  # Linux: ru_maxrss em KB
            if rss_mb > _RSS_WARN_MB:
                logger.warning(
                    f"[MEMORY LEAK DETECTOR] RSS={rss_mb:.0f} MB excede "
                    f"limiar de {_RSS_WARN_MB:.0f} MB — possível vazamento de memória"
                )
            else:
                logger.debug(f"[MEMORY] RSS={rss_mb:.0f} MB")
        except Exception as exc:  # pragma: no cover
            logger.debug(f"RSS check failed: {exc}")


class SlowRequestMiddleware:
    """Alerta quando uma request leva mais que _SLOW_REQUEST_WARN_S segundos."""

    def __init__(self, app) -> None:
        self._app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self._app(scope, receive, send)
            return

        start = time.monotonic()
        try:
            await self._app(scope, receive, send)
        finally:
            elapsed = time.monotonic() - start
            if elapsed > _SLOW_REQUEST_WARN_S:  # pragma: no cover
                path = scope.get("path", "")
                method = scope.get("method", "")
                logger.warning(
                    f"[MEMORY LEAK DETECTOR] {method} {path} levou {elapsed:.1f}s "
                    f"— possível conexão retida por muito tempo"
                )
