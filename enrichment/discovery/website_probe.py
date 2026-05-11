"""Probe HTTP/HTTPS de domínios candidatos com limites estritos.

Política do projeto (spec): UA identificável, timeouts curtos, sem evasão de
anti-bot, sem cookies. Detecta páginas estacionadas/parked para descartá-las
antes de consumir orçamento de crawl.
"""
import asyncio
import concurrent.futures
import socket
from dataclasses import dataclass
from typing import Optional

import httpx

# Dedicated thread pool for DNS lookups. The default asyncio executor fills with
# zombie threads when wait_for times out (the underlying thread keeps running until
# the OS DNS timeout of 5-10s). A large dedicated pool prevents this from blocking
# all other executor tasks.
_DNS_EXECUTOR = concurrent.futures.ThreadPoolExecutor(max_workers=200, thread_name_prefix="dns")

DEFAULT_USER_AGENT = "CNPJDiscoveryBot/1.0 (+https://cnpj-discovery.example/crawler)"
DEFAULT_TIMEOUT_SECONDS = 12.0
DEFAULT_MAX_BYTES = 2_000_000
DEFAULT_MAX_REDIRECTS = 4

PARKED_KEYWORDS = (
    "this domain is for sale",
    "domain is for sale",
    "buy this domain",
    "domain parking",
    "parked domain",
    "este dominio esta a venda",
    "este dominio está à venda",
    "domínio à venda",
    "comprar este dominio",
    "comprar este domínio",
    "registered at namecheap",
)


@dataclass(frozen=True)
class ProbeResult:
    domain: str
    final_url: str
    http_status: int
    content_type: str
    body: str
    parked: bool
    error: Optional[str] = None

    @property
    def ok(self) -> bool:
        return self.error is None and 200 <= self.http_status < 400


def is_parked(html: str) -> bool:
    if not html:
        return False
    lower = html.lower()
    return any(keyword in lower for keyword in PARKED_KEYWORDS)


async def probe_domain(
    domain: str,
    *,
    client: httpx.AsyncClient,
    max_bytes: int = DEFAULT_MAX_BYTES,
) -> ProbeResult:
    """Tenta HTTPS primeiro, com fallback para HTTP. Nunca lança."""
    last_error: Optional[str] = None
    for scheme in ("https", "http"):
        url = f"{scheme}://{domain}/"
        try:
            response = await client.get(url, follow_redirects=True)
        except httpx.HTTPError as exc:
            last_error = f"{type(exc).__name__}: {exc}"
            continue

        body_bytes = response.content[:max_bytes]
        encoding = response.encoding or "utf-8"
        body = body_bytes.decode(encoding, errors="replace")
        return ProbeResult(
            domain=domain,
            final_url=str(response.url),
            http_status=response.status_code,
            content_type=response.headers.get("content-type", ""),
            body=body,
            parked=is_parked(body),
        )
    return ProbeResult(
        domain=domain,
        final_url=f"https://{domain}/",
        http_status=0,
        content_type="",
        body="",
        parked=False,
        error=last_error or "no response",
    )


async def dns_exists(domain: str, *, timeout: float = 0.5) -> bool:
    """Returns True if domain has at least one A/AAAA DNS record.

    Uses a dedicated large thread pool to avoid clogging the default executor
    with zombie threads (wait_for cancels the Future but the thread keeps
    blocking until the OS DNS timeout of 5-10s).
    """
    loop = asyncio.get_running_loop()
    try:
        await asyncio.wait_for(
            loop.run_in_executor(_DNS_EXECUTOR, socket.getaddrinfo, domain, None),
            timeout=timeout,
        )
        return True
    except (OSError, asyncio.TimeoutError):
        return False


def make_default_client(*, user_agent: str = DEFAULT_USER_AGENT) -> httpx.AsyncClient:
    """Factory com bounds adequados; sempre fechar com `async with`."""
    return httpx.AsyncClient(
        headers={"User-Agent": user_agent},
        timeout=httpx.Timeout(DEFAULT_TIMEOUT_SECONDS),
        max_redirects=DEFAULT_MAX_REDIRECTS,
        follow_redirects=True,
    )
