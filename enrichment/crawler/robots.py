"""Fetch + parse + cache de robots.txt.

Mantemos o raw em memória durante o ciclo do worker (cache local) e
gravamos status/crawl_delay em `paid_enrichment.crawl_hosts` para
visibilidade. A política é estritamente *robots-aware*: nunca crawl
fora do que o robots.txt permite.
"""
from dataclasses import dataclass
from urllib.robotparser import RobotFileParser

import httpx


@dataclass(frozen=True)
class RobotsRules:
    domain: str
    raw: str
    crawl_delay: float | None
    fetched_status: int

    def can_fetch(self, url: str, user_agent: str) -> bool:
        if not self.raw:
            return True  # ausência de robots.txt = permitido (RFC 9309)
        parser = RobotFileParser()
        parser.parse(self.raw.splitlines())
        return parser.can_fetch(user_agent, url)


_SQL_UPSERT_HOST_ROBOTS = """
    INSERT INTO paid_enrichment.crawl_hosts (
        domain, robots_status, robots_checked_at, crawl_delay_seconds
    )
    VALUES ($1, $2, now(), $3)
    ON CONFLICT (domain) DO UPDATE SET
        robots_status = EXCLUDED.robots_status,
        robots_checked_at = EXCLUDED.robots_checked_at,
        crawl_delay_seconds = EXCLUDED.crawl_delay_seconds
"""


async def fetch_robots(
    domain: str,
    *,
    client: httpx.AsyncClient,
    user_agent: str,
) -> RobotsRules:
    """GET /robots.txt; em qualquer falha retorna `raw=""` (permitido)."""
    url = f"https://{domain}/robots.txt"
    try:
        response = await client.get(url, follow_redirects=True)
    except httpx.HTTPError:
        return RobotsRules(domain=domain, raw="", crawl_delay=None, fetched_status=0)

    if response.status_code >= 400:
        return RobotsRules(
            domain=domain,
            raw="",
            crawl_delay=None,
            fetched_status=response.status_code,
        )

    raw = response.text
    parser = RobotFileParser()
    parser.parse(raw.splitlines())
    delay = parser.crawl_delay(user_agent)

    return RobotsRules(
        domain=domain,
        raw=raw,
        crawl_delay=float(delay) if delay is not None else None,
        fetched_status=response.status_code,
    )


def _status_text(http_status: int) -> str:
    if 200 <= http_status < 400:
        return "ok"
    if http_status == 404:
        return "missing"
    if http_status == 0:
        return "unreachable"
    return f"http_{http_status}"


async def persist_host_robots(pool, rules: RobotsRules) -> None:
    async with pool.acquire() as conn:
        await conn.execute(
            _SQL_UPSERT_HOST_ROBOTS,
            rules.domain,
            _status_text(rules.fetched_status),
            rules.crawl_delay,
        )
