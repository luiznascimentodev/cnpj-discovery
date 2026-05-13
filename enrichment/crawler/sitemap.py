"""Sitemap-based URL discovery.

Replaces the static path-guessing heuristic (which generated ~70% HTTP 404s
on real domains) with actual URLs from sitemap.xml. Falls back to homepage
only when no sitemap is available — guessing paths like /empresa or
/atendimento is worse than just crawling /.

API surface kept small:

- fetch_sitemap_urls(client, base_url) -> list[str]
    Returns sitemap URLs that look contact/about relevant. Empty list on any
    fetch/parse error.
- discover_crawl_urls(client, base_url) -> list[str]
    The high-level entry point: returns the list of URLs to crawl for a
    domain. Always includes the homepage. Adds sitemap-discovered URLs when
    available. Caps at MAX_URLS_PER_DOMAIN.
"""
from __future__ import annotations

import xml.etree.ElementTree as ET
from typing import Iterable
from urllib.parse import urljoin, urlparse

import httpx
from loguru import logger

SITEMAP_PATHS = ["/sitemap.xml", "/sitemap_index.xml", "/sitemap-index.xml"]
SITEMAP_TIMEOUT = 3.0
SITEMAP_MAX_BYTES = 2_000_000  # 2 MB hard cap
MAX_URLS_PER_DOMAIN = 6
MAX_SITEMAPS_TO_FOLLOW = 3

_CONTACT_PAGE_SEGMENTS = frozenset({
    "atendimento",
    "contact",
    "contato",
    "fale-conosco",
    "ouvidoria",
    "sac",
    "suporte",
})

_ABOUT_PAGE_SEGMENTS = frozenset({
    "empresa",
    "institucional",
    "quem-somos",
    "sobre",
    "sobre-a-empresa",
    "sobre-nos",
})

_XML_NS = "{http://www.sitemaps.org/schemas/sitemap/0.9}"


def _strip_namespace(tag: str) -> str:
    return tag.split("}", 1)[1] if "}" in tag else tag


def _parse_sitemap_xml(content: bytes) -> tuple[list[str], list[str]]:
    """Returns (page_urls, nested_sitemap_urls). Empty lists on parse error."""
    try:
        root = ET.fromstring(content)
    except ET.ParseError as exc:
        logger.debug("sitemap_parse_error error={}", exc)
        return [], []
    page_urls: list[str] = []
    nested: list[str] = []
    root_tag = _strip_namespace(root.tag)
    if root_tag == "sitemapindex":
        for sitemap in root:
            for child in sitemap:
                if _strip_namespace(child.tag) == "loc" and child.text:
                    nested.append(child.text.strip())
    elif root_tag == "urlset":
        for url_elem in root:
            for child in url_elem:
                if _strip_namespace(child.tag) == "loc" and child.text:
                    page_urls.append(child.text.strip())
    return page_urls, nested


def _is_relevant_path(path: str) -> bool:
    segments = [segment.lower() for segment in path.strip("/").split("/") if segment]
    if not segments:
        return False
    if any(segment in _CONTACT_PAGE_SEGMENTS for segment in segments):
        return True
    return len(segments) == 1 and segments[0] in _ABOUT_PAGE_SEGMENTS


async def _fetch_one(client: httpx.AsyncClient, url: str) -> bytes | None:
    try:
        response = await client.get(url, timeout=SITEMAP_TIMEOUT, follow_redirects=True)
    except httpx.HTTPError as exc:
        logger.debug("sitemap_fetch_error url={} error={}", url, exc)
        return None
    if response.status_code != 200:
        return None
    content = response.content
    if len(content) > SITEMAP_MAX_BYTES:
        return None
    return content


def _filter_relevant(urls: Iterable[str], base_root: str, base_host: str) -> list[str]:
    """Keep only same-host URLs with contact-relevant keywords."""
    out: list[str] = []
    for url in urls:
        normalized = urljoin(base_root + "/", url.strip())
        parsed = urlparse(normalized)
        if parsed.netloc != base_host:
            continue
        if not _is_relevant_path(parsed.path):
            continue
        out.append(parsed._replace(fragment="").geturl())
    return out


async def fetch_sitemap_urls(client: httpx.AsyncClient, base_url: str) -> list[str]:
    """Try common sitemap locations, follow up to MAX_SITEMAPS_TO_FOLLOW nested
    indices, and return contact-relevant page URLs (deduped, capped)."""
    parsed_base = urlparse(base_url if "://" in base_url else f"https://{base_url}")
    base_host = parsed_base.netloc
    if not base_host:
        return []
    base_root = f"{parsed_base.scheme}://{base_host}"

    queue: list[str] = [urljoin(base_root + "/", p.lstrip("/")) for p in SITEMAP_PATHS]
    seen_sitemaps: set[str] = set()
    page_urls: list[str] = []
    follow_budget = MAX_SITEMAPS_TO_FOLLOW

    while queue and follow_budget > 0:
        sitemap_url = queue.pop(0)
        if sitemap_url in seen_sitemaps:
            continue
        seen_sitemaps.add(sitemap_url)
        content = await _fetch_one(client, sitemap_url)
        if not content:
            continue
        pages, nested = _parse_sitemap_xml(content)
        page_urls.extend(pages)
        for nested_url in nested:
            if nested_url not in seen_sitemaps:
                queue.append(nested_url)
        follow_budget -= 1
        if len(page_urls) >= MAX_URLS_PER_DOMAIN * 10:
            break

    relevant = _filter_relevant(page_urls, base_root, base_host)
    # Dedupe while preserving order
    seen: set[str] = set()
    deduped: list[str] = []
    for url in relevant:
        if url not in seen:
            seen.add(url)
            deduped.append(url)
        if len(deduped) >= MAX_URLS_PER_DOMAIN:
            break
    return deduped


async def discover_crawl_urls(client: httpx.AsyncClient, base_url: str) -> list[str]:
    """Always returns the homepage; appends sitemap-derived URLs if any.
    Capped at MAX_URLS_PER_DOMAIN total."""
    parsed = urlparse(base_url if "://" in base_url else f"https://{base_url}")
    if not parsed.netloc:
        return []
    homepage = f"{parsed.scheme}://{parsed.netloc}/"
    urls: list[str] = [homepage]
    sitemap_urls = await fetch_sitemap_urls(client, base_url)
    for url in sitemap_urls:
        if url not in urls:
            urls.append(url)
        if len(urls) >= MAX_URLS_PER_DOMAIN:
            break
    return urls
