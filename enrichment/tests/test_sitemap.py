from unittest.mock import AsyncMock, MagicMock

import httpx
import pytest

from crawler import sitemap


def _xml_urlset(urls: list[str]) -> bytes:
    locs = "".join(f"<url><loc>{u}</loc></url>" for u in urls)
    return (
        '<?xml version="1.0" encoding="UTF-8"?>'
        '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">'
        f"{locs}</urlset>"
    ).encode("utf-8")


def _xml_sitemap_index(urls: list[str]) -> bytes:
    locs = "".join(f"<sitemap><loc>{u}</loc></sitemap>" for u in urls)
    return (
        '<?xml version="1.0" encoding="UTF-8"?>'
        '<sitemapindex xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">'
        f"{locs}</sitemapindex>"
    ).encode("utf-8")


class FakeResponse:
    def __init__(self, status_code: int, content: bytes = b""):
        self.status_code = status_code
        self.content = content


def _fake_client(responses: dict[str, FakeResponse | Exception]) -> MagicMock:
    """Builds a fake AsyncClient whose .get() returns mapped responses."""
    client = MagicMock()
    async def fake_get(url, **kwargs):
        result = responses.get(url)
        if result is None:
            return FakeResponse(404)
        if isinstance(result, Exception):
            raise result
        return result
    client.get = fake_get
    return client


class TestParseSitemapXml:
    def test_parses_urlset(self):
        content = _xml_urlset(["https://x.com/a", "https://x.com/contato"])
        pages, nested = sitemap._parse_sitemap_xml(content)
        assert pages == ["https://x.com/a", "https://x.com/contato"]
        assert nested == []

    def test_parses_sitemap_index(self):
        content = _xml_sitemap_index(["https://x.com/sub.xml"])
        pages, nested = sitemap._parse_sitemap_xml(content)
        assert pages == []
        assert nested == ["https://x.com/sub.xml"]

    def test_returns_empty_on_parse_error(self):
        pages, nested = sitemap._parse_sitemap_xml(b"not xml")
        assert pages == []
        assert nested == []

    def test_ignores_unknown_root(self):
        pages, nested = sitemap._parse_sitemap_xml(b"<root><foo/></root>")
        assert pages == []
        assert nested == []


class TestFetchOne:
    @pytest.mark.asyncio
    async def test_returns_content_on_200(self):
        client = _fake_client({"https://x.com/sitemap.xml": FakeResponse(200, b"<x/>")})
        result = await sitemap._fetch_one(client, "https://x.com/sitemap.xml")
        assert result == b"<x/>"

    @pytest.mark.asyncio
    async def test_returns_none_on_non_200(self):
        client = _fake_client({"https://x.com/sitemap.xml": FakeResponse(404)})
        result = await sitemap._fetch_one(client, "https://x.com/sitemap.xml")
        assert result is None

    @pytest.mark.asyncio
    async def test_returns_none_on_http_error(self):
        client = _fake_client({"https://x.com/sitemap.xml": httpx.ConnectError("nope")})
        result = await sitemap._fetch_one(client, "https://x.com/sitemap.xml")
        assert result is None

    @pytest.mark.asyncio
    async def test_returns_none_when_oversized(self):
        big = b"x" * (sitemap.SITEMAP_MAX_BYTES + 1)
        client = _fake_client({"https://x.com/sitemap.xml": FakeResponse(200, big)})
        result = await sitemap._fetch_one(client, "https://x.com/sitemap.xml")
        assert result is None


class TestFilterRelevant:
    def test_keeps_only_same_host_with_keywords(self):
        urls = [
            "https://x.com/contato",
            "https://other.com/contato",
            "https://x.com/blog/post-1",
            "https://x.com/sobre-a-empresa",
        ]
        result = sitemap._filter_relevant(urls, "https://x.com", "x.com")
        assert "https://x.com/contato" in result
        assert "https://x.com/sobre-a-empresa" in result
        assert "https://other.com/contato" not in result
        assert "https://x.com/blog/post-1" not in result

    def test_normalizes_relative_paths(self):
        result = sitemap._filter_relevant(["/contato"], "https://x.com", "x.com")
        assert result == ["https://x.com/contato"]

    def test_removes_fragments(self):
        result = sitemap._filter_relevant(["/contato#form"], "https://x.com", "x.com")
        assert result == ["https://x.com/contato"]

    def test_does_not_match_keyword_inside_unrelated_words(self):
        urls = [
            "https://x.com/webstories/destinos-marcantes.html",
            "https://x.com/blog/celebrando-25-anos",
            "https://x.com/acontece/all-about-bears/",
            "https://x.com/acontece/team-steam/",
            "https://x.com/para-sua-empresa/",
            "https://x.com/sobre-nos/",
        ]
        result = sitemap._filter_relevant(urls, "https://x.com", "x.com")
        assert result == ["https://x.com/sobre-nos/"]

    def test_keeps_contact_page_nested_under_institutional(self):
        result = sitemap._filter_relevant(
            ["https://x.com/institucional/contato/"],
            "https://x.com",
            "x.com",
        )
        assert result == ["https://x.com/institucional/contato/"]


class TestFetchSitemapUrls:
    @pytest.mark.asyncio
    async def test_returns_relevant_urls_from_urlset(self):
        client = _fake_client({
            "https://x.com/sitemap.xml": FakeResponse(200, _xml_urlset([
                "https://x.com/contato",
                "https://x.com/blog/post",
                "https://x.com/sobre",
            ])),
        })
        urls = await sitemap.fetch_sitemap_urls(client, "https://x.com")
        assert urls == ["https://x.com/contato", "https://x.com/sobre"]

    @pytest.mark.asyncio
    async def test_follows_sitemap_index(self):
        client = _fake_client({
            "https://x.com/sitemap.xml": FakeResponse(200, _xml_sitemap_index([
                "https://x.com/sub1.xml",
            ])),
            "https://x.com/sub1.xml": FakeResponse(200, _xml_urlset([
                "https://x.com/contato",
            ])),
        })
        urls = await sitemap.fetch_sitemap_urls(client, "https://x.com")
        assert urls == ["https://x.com/contato"]

    @pytest.mark.asyncio
    async def test_returns_empty_when_no_sitemap(self):
        client = _fake_client({})
        urls = await sitemap.fetch_sitemap_urls(client, "https://x.com")
        assert urls == []

    @pytest.mark.asyncio
    async def test_caps_at_max_urls(self):
        many = [f"https://x.com/contato/departamento-{i}" for i in range(20)]
        client = _fake_client({
            "https://x.com/sitemap.xml": FakeResponse(200, _xml_urlset(many)),
        })
        urls = await sitemap.fetch_sitemap_urls(client, "https://x.com")
        assert len(urls) == sitemap.MAX_URLS_PER_DOMAIN

    @pytest.mark.asyncio
    async def test_dedupes_urls(self):
        client = _fake_client({
            "https://x.com/sitemap.xml": FakeResponse(200, _xml_urlset([
                "https://x.com/contato",
                "https://x.com/contato",
                "https://x.com/sobre",
            ])),
        })
        urls = await sitemap.fetch_sitemap_urls(client, "https://x.com")
        assert urls == ["https://x.com/contato", "https://x.com/sobre"]

    @pytest.mark.asyncio
    async def test_handles_bare_domain_input(self):
        client = _fake_client({
            "https://x.com/sitemap.xml": FakeResponse(200, _xml_urlset([
                "https://x.com/contato",
            ])),
        })
        urls = await sitemap.fetch_sitemap_urls(client, "x.com")
        assert urls == ["https://x.com/contato"]

    @pytest.mark.asyncio
    async def test_returns_empty_when_no_host(self):
        client = _fake_client({})
        urls = await sitemap.fetch_sitemap_urls(client, "://broken")
        assert urls == []

    @pytest.mark.asyncio
    async def test_avoids_nested_loops_via_seen_set(self):
        client = _fake_client({
            "https://x.com/sitemap.xml": FakeResponse(200, _xml_sitemap_index([
                "https://x.com/sitemap.xml",  # self-reference
            ])),
        })
        urls = await sitemap.fetch_sitemap_urls(client, "https://x.com")
        assert urls == []

    @pytest.mark.asyncio
    async def test_skips_already_seen_sitemap_urls(self, monkeypatch):
        monkeypatch.setattr(sitemap, "SITEMAP_PATHS", ["/sitemap.xml", "/sitemap.xml"])
        client = _fake_client({})
        urls = await sitemap.fetch_sitemap_urls(client, "https://x.com")
        assert urls == []

    @pytest.mark.asyncio
    async def test_stops_following_after_max_sitemaps(self):
        # Build a chain of nested indexes longer than MAX_SITEMAPS_TO_FOLLOW
        client_map = {}
        for i in range(10):
            url = f"https://x.com/s{i}.xml"
            next_url = f"https://x.com/s{i+1}.xml"
            client_map[url] = FakeResponse(200, _xml_sitemap_index([next_url]))
        # The starting sitemap.xml points to s0.xml
        client_map["https://x.com/sitemap.xml"] = FakeResponse(
            200, _xml_sitemap_index(["https://x.com/s0.xml"])
        )
        client = _fake_client(client_map)
        urls = await sitemap.fetch_sitemap_urls(client, "https://x.com")
        assert urls == []  # No page URLs ever materialize

    @pytest.mark.asyncio
    async def test_stops_fetching_after_large_page_url_batch(self):
        many = [
            f"https://x.com/contato/departamento-{i}"
            for i in range(sitemap.MAX_URLS_PER_DOMAIN * 10 + 1)
        ]
        client = _fake_client({
            "https://x.com/sitemap.xml": FakeResponse(200, _xml_urlset(many)),
        })
        urls = await sitemap.fetch_sitemap_urls(client, "https://x.com")
        assert len(urls) == sitemap.MAX_URLS_PER_DOMAIN


class TestDiscoverCrawlUrls:
    @pytest.mark.asyncio
    async def test_always_includes_homepage(self):
        client = _fake_client({})
        urls = await sitemap.discover_crawl_urls(client, "https://x.com")
        assert urls == ["https://x.com/"]

    @pytest.mark.asyncio
    async def test_appends_sitemap_urls(self):
        client = _fake_client({
            "https://x.com/sitemap.xml": FakeResponse(200, _xml_urlset([
                "https://x.com/contato",
                "https://x.com/sobre",
            ])),
        })
        urls = await sitemap.discover_crawl_urls(client, "https://x.com")
        assert urls[0] == "https://x.com/"
        assert "https://x.com/contato" in urls
        assert "https://x.com/sobre" in urls

    @pytest.mark.asyncio
    async def test_returns_empty_for_broken_url(self):
        client = _fake_client({})
        urls = await sitemap.discover_crawl_urls(client, "://broken")
        assert urls == []

    @pytest.mark.asyncio
    async def test_does_not_duplicate_homepage(self):
        client = _fake_client({
            "https://x.com/sitemap.xml": FakeResponse(200, _xml_urlset([
                "https://x.com/",
                "https://x.com/contato",
            ])),
        })
        urls = await sitemap.discover_crawl_urls(client, "https://x.com")
        # Note: the homepage from sitemap won't match the keyword filter, so it's
        # already filtered out. But the test guards against duplicate-add if it
        # ever appears.
        assert urls.count("https://x.com/") == 1

    @pytest.mark.asyncio
    async def test_caps_at_max_urls(self):
        many = [f"https://x.com/contato/departamento-{i}" for i in range(20)]
        client = _fake_client({
            "https://x.com/sitemap.xml": FakeResponse(200, _xml_urlset(many)),
        })
        urls = await sitemap.discover_crawl_urls(client, "https://x.com")
        assert len(urls) == sitemap.MAX_URLS_PER_DOMAIN
