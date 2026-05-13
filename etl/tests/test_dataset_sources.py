from datetime import datetime, timezone
from unittest.mock import MagicMock, patch

import pytest

from dataset_sources import (
    DatasetFile,
    DatasetSnapshot,
    choose_load_snapshot,
    discover_dados_gov_catalog,
    discover_rf_http_index,
    discover_rf_webdav,
    parse_http_index,
    parse_snapshot_links,
)
from downloader import RFFile


HTTP_ROOT = """
<html><body>
<a href="2024-01/">2024-01/</a>
<a href="2024-03/">2024-03/</a>
</body></html>
"""

HTTP_FILES = """
<html><body><pre>
<a href="Empresas0.zip">Empresas0.zip</a> 2024-03-01 10:00 10M
<a href="Estabelecimentos0.zip">Estabelecimentos0.zip</a> 2024-03-01 11:00 2G
<a href="README.txt">README.txt</a> 2024-03-01 11:00 1K
</pre></body></html>
"""


class FakeResponse:
    def __init__(self, text, headers=None):
        self.text = text
        self.headers = headers or {}

    def raise_for_status(self):
        return None


class FakeClient:
    def __init__(self, responses):
        self.responses = list(responses)
        self.urls = []

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, traceback):
        return False

    def get(self, url):
        self.urls.append(url)
        return self.responses.pop(0)


class TestDatasetSources:
    def test_parse_snapshot_links_returns_sorted_months(self):
        assert parse_snapshot_links(HTTP_ROOT) == ["2024-01", "2024-03"]

    def test_parse_http_index_returns_zip_files(self):
        snapshot = parse_http_index(
            HTTP_FILES,
            base_url="https://example.test/2024-03/",
            snapshot_key="2024-03",
        )

        assert snapshot.source_name == "rf_http_index"
        assert snapshot.file_count == 2
        assert snapshot.total_size_bytes == 10 * 1024**2 + 2 * 1024**3
        assert snapshot.last_modified_max == datetime(2024, 3, 1, 11, 0, tzinfo=timezone.utc)
        assert snapshot.manifest_hash

    def test_choose_load_snapshot_prefers_bulk_latest(self):
        webdav = DatasetSnapshot(
            source_name="rf_webdav",
            snapshot_key="2024-02",
            source_url="webdav",
            files=[DatasetFile("a.zip", "a", 1)],
        )
        http = DatasetSnapshot(
            source_name="rf_http_index",
            snapshot_key="2024-03",
            source_url="http",
            files=[DatasetFile("a.zip", "a", 2)],
        )
        catalog = DatasetSnapshot(
            source_name="dados_gov_catalog",
            snapshot_key="2024-04",
            source_url="catalog",
            files=[DatasetFile("catalog.html", "catalog", 3)],
        )

        assert choose_load_snapshot([webdav, http, catalog]) is http

    def test_choose_load_snapshot_returns_none_without_bulk_source(self):
        catalog = DatasetSnapshot(
            source_name="dados_gov_catalog",
            snapshot_key="2024-04",
            source_url="catalog",
            files=[DatasetFile("catalog.html", "catalog", 3)],
        )
        assert choose_load_snapshot([catalog]) is None

    def test_discover_rf_http_index_fetches_latest_snapshot(self):
        client = FakeClient([FakeResponse(HTTP_ROOT), FakeResponse(HTTP_FILES)])
        with patch("dataset_sources.httpx.Client", return_value=client):
            snapshot = discover_rf_http_index()

        assert snapshot.snapshot_key == "2024-03"
        assert client.urls[-1].endswith("/2024-03/")

    def test_discover_rf_http_index_handles_root_files(self):
        client = FakeClient([FakeResponse(HTTP_FILES)])
        with patch("dataset_sources.httpx.Client", return_value=client):
            snapshot = discover_rf_http_index()

        assert snapshot.snapshot_key == "root"
        assert snapshot.file_count == 2

    def test_discover_rf_webdav_uses_existing_downloader(self):
        rf_file = RFFile(
            name="Empresas0.zip",
            last_modified=datetime(2024, 3, 1, tzinfo=timezone.utc),
            size=123,
            url_path="Dados/Cadastros/CNPJ/2024-03/Empresas0.zip",
        )
        with patch("dataset_sources.list_rf_files", return_value=[rf_file]):
            snapshot = discover_rf_webdav()

        assert snapshot.snapshot_key == "2024-03"
        assert snapshot.files[0].file_name == "Empresas0.zip"

    def test_discover_dados_gov_catalog_records_metadata(self):
        response = FakeResponse(
            "<html>CNPJ</html>",
            headers={"etag": "abc", "last-modified": "Mon, 01 Jan 2024 00:00:00 GMT"},
        )
        with patch("dataset_sources.httpx.Client", return_value=FakeClient([response])):
            snapshot = discover_dados_gov_catalog()

        assert snapshot.source_name == "dados_gov_catalog"
        assert snapshot.files[0].etag == "abc"
