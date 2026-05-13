"""Testes para etl/downloader.py — sem requisições de rede reais."""
import xml.etree.ElementTree as ET
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import MagicMock, patch, mock_open
import pytest
import httpx

from downloader import RFFile, list_rf_files, _download_with_resume, _parse_propfind_response, download_file


# ─── Fixtures ────────────────────────────────────────────────────────────────

SAMPLE_PROPFIND_XML = """<?xml version="1.0"?>
<d:multistatus xmlns:d="DAV:">
  <d:response>
    <d:href>/public.php/webdav/</d:href>
    <d:propstat>
      <d:prop>
        <d:resourcetype><d:collection/></d:resourcetype>
        <d:getlastmodified>Mon, 01 Jan 2024 00:00:00 GMT</d:getlastmodified>
        <d:getcontentlength>0</d:getcontentlength>
      </d:prop>
    </d:propstat>
  </d:response>
  <d:response>
    <d:href>/public.php/webdav/Empresas0.zip</d:href>
    <d:propstat>
      <d:prop>
        <d:resourcetype/>
        <d:getlastmodified>Mon, 01 Jan 2024 12:00:00 GMT</d:getlastmodified>
        <d:getcontentlength>123456789</d:getcontentlength>
      </d:prop>
    </d:propstat>
  </d:response>
  <d:response>
    <d:href>/public.php/webdav/Estabelecimentos0.zip</d:href>
    <d:propstat>
      <d:prop>
        <d:resourcetype/>
        <d:getlastmodified>Tue, 02 Jan 2024 06:00:00 GMT</d:getlastmodified>
        <d:getcontentlength>987654321</d:getcontentlength>
      </d:prop>
    </d:propstat>
  </d:response>
  <d:response>
    <d:href>/public.php/webdav/README.txt</d:href>
    <d:propstat>
      <d:prop>
        <d:getlastmodified>Mon, 01 Jan 2024 00:00:00 GMT</d:getlastmodified>
        <d:getcontentlength>1024</d:getcontentlength>
      </d:prop>
    </d:propstat>
  </d:response>
</d:multistatus>"""

@pytest.fixture
def sample_rf_file():
    return RFFile(
        name="Empresas0.zip",
        last_modified=datetime(2024, 1, 1, 12, 0, tzinfo=timezone.utc),
        size=123456789,
    )


# ─── Testes de _parse_propfind_response ──────────────────────────────────────

class TestParsePropfindResponse:
    def test_returns_only_zip_files(self):
        files = _parse_propfind_response(SAMPLE_PROPFIND_XML)
        assert all(f.name.endswith(".zip") for f in files)

    def test_ignores_directory_entry(self):
        files = _parse_propfind_response(SAMPLE_PROPFIND_XML)
        names = [f.name for f in files]
        assert "" not in names
        assert "/" not in names

    def test_ignores_non_zip_files(self):
        files = _parse_propfind_response(SAMPLE_PROPFIND_XML)
        names = [f.name for f in files]
        assert "README.txt" not in names

    def test_parses_two_zip_files(self):
        files = _parse_propfind_response(SAMPLE_PROPFIND_XML)
        assert len(files) == 2

    def test_parses_file_name(self):
        files = _parse_propfind_response(SAMPLE_PROPFIND_XML)
        names = [f.name for f in files]
        assert "Empresas0.zip" in names
        assert "Estabelecimentos0.zip" in names

    def test_parses_file_size(self):
        files = _parse_propfind_response(SAMPLE_PROPFIND_XML)
        empresas = next(f for f in files if f.name == "Empresas0.zip")
        assert empresas.size == 123456789

    def test_files_sorted_by_name(self):
        files = _parse_propfind_response(SAMPLE_PROPFIND_XML)
        names = [f.name for f in files]
        assert names == sorted(names)

    def test_handles_missing_prop(self):
        xml = """<?xml version="1.0"?>
<d:multistatus xmlns:d="DAV:">
  <d:response>
    <d:href>/public.php/webdav/BadFile.zip</d:href>
  </d:response>
</d:multistatus>"""
        files = _parse_propfind_response(xml)
        assert files == []

    def test_handles_invalid_date(self):
        xml = """<?xml version="1.0"?>
<d:multistatus xmlns:d="DAV:">
  <d:response>
    <d:href>/public.php/webdav/File.zip</d:href>
    <d:propstat>
      <d:prop>
        <d:getlastmodified>INVALID_DATE</d:getlastmodified>
        <d:getcontentlength>100</d:getcontentlength>
      </d:prop>
    </d:propstat>
  </d:response>
</d:multistatus>"""
        files = _parse_propfind_response(xml)
        assert len(files) == 1
        assert files[0].last_modified == datetime.min

    def test_handles_empty_date(self):
        xml = """<?xml version="1.0"?>
<d:multistatus xmlns:d="DAV:">
  <d:response>
    <d:href>/public.php/webdav/File.zip</d:href>
    <d:propstat>
      <d:prop>
        <d:getlastmodified></d:getlastmodified>
        <d:getcontentlength>100</d:getcontentlength>
      </d:prop>
    </d:propstat>
  </d:response>
</d:multistatus>"""
        files = _parse_propfind_response(xml)
        assert len(files) == 1
        assert files[0].last_modified == datetime.min


# ─── Testes de list_rf_files ─────────────────────────────────────────────────

class TestListRFFiles:
    def test_calls_propfind_and_returns_files(self, mocker):
        mock_resp = MagicMock()
        mock_resp.raise_for_status = MagicMock()
        mock_resp.text = SAMPLE_PROPFIND_XML

        mock_client = MagicMock()
        mock_client.__enter__ = MagicMock(return_value=mock_client)
        mock_client.__exit__ = MagicMock(return_value=False)
        mock_client.request = MagicMock(return_value=mock_resp)

        mocker.patch("downloader.httpx.Client", return_value=mock_client)

        files = list_rf_files()
        assert len(files) == 2
        mock_client.request.assert_called_once()
        call_args = mock_client.request.call_args
        assert call_args[0][0] == "PROPFIND"

    def test_raises_on_http_error(self, mocker):
        mock_resp = MagicMock()
        mock_resp.raise_for_status.side_effect = httpx.HTTPStatusError(
            "404", request=MagicMock(), response=MagicMock()
        )
        mock_client = MagicMock()
        mock_client.__enter__ = MagicMock(return_value=mock_client)
        mock_client.__exit__ = MagicMock(return_value=False)
        mock_client.request = MagicMock(return_value=mock_resp)
        mocker.patch("downloader.httpx.Client", return_value=mock_client)

        with pytest.raises(httpx.HTTPStatusError):
            list_rf_files()


# ─── Testes de download_file ─────────────────────────────────────────────────

class TestDownloadFile:
    def test_creates_file_in_dest_dir(self, tmp_path, sample_rf_file, mocker):
        mock_response = MagicMock()
        mock_response.raise_for_status = MagicMock()
        mock_response.iter_bytes = MagicMock(return_value=iter([b"fake_zip_content"]))
        mock_response.__enter__ = MagicMock(return_value=mock_response)
        mock_response.__exit__ = MagicMock(return_value=False)

        mocker.patch("downloader.httpx.stream", return_value=mock_response)

        result = download_file(sample_rf_file, str(tmp_path))
        assert result == tmp_path / "Empresas0.zip"
        assert result.exists()
        assert result.read_bytes() == b"fake_zip_content"

    def test_creates_dest_dir_if_not_exists(self, tmp_path, sample_rf_file, mocker):
        new_dir = tmp_path / "subdir" / "data"
        mock_response = MagicMock()
        mock_response.raise_for_status = MagicMock()
        mock_response.iter_bytes = MagicMock(return_value=iter([b"data"]))
        mock_response.__enter__ = MagicMock(return_value=mock_response)
        mock_response.__exit__ = MagicMock(return_value=False)
        mocker.patch("downloader.httpx.stream", return_value=mock_response)

        result = download_file(sample_rf_file, str(new_dir))
        assert result.exists()

    def test_keeps_partial_file_on_error_for_resume(self, tmp_path, sample_rf_file, mocker):
        mock_response = MagicMock()
        mock_response.raise_for_status = MagicMock()
        mock_response.iter_bytes = MagicMock(side_effect=ConnectionError("network error"))
        mock_response.__enter__ = MagicMock(return_value=mock_response)
        mock_response.__exit__ = MagicMock(return_value=False)
        mocker.patch("downloader.httpx.stream", return_value=mock_response)

        # Cria arquivo parcial para simular download interrompido
        partial = tmp_path / "Empresas0.zip"
        partial.write_bytes(b"partial")

        with pytest.raises(ConnectionError):
            _download_with_resume.__wrapped__(sample_rf_file, partial)  # bypass retry

        assert partial.exists()

    def test_returns_path_to_downloaded_file(self, tmp_path, sample_rf_file, mocker):
        mock_response = MagicMock()
        mock_response.raise_for_status = MagicMock()
        mock_response.iter_bytes = MagicMock(return_value=iter([b"zip_data"]))
        mock_response.__enter__ = MagicMock(return_value=mock_response)
        mock_response.__exit__ = MagicMock(return_value=False)
        mocker.patch("downloader.httpx.stream", return_value=mock_response)

        result = download_file(sample_rf_file, str(tmp_path))
        assert isinstance(result, Path)
        assert result.name == "Empresas0.zip"

    def test_empty_partial_file_is_kept_for_resume_when_stream_fails(self, tmp_path, sample_rf_file, mocker):
        """Covers the branch where dest does not exist when exception is raised."""
        mock_response = MagicMock()
        mock_response.raise_for_status = MagicMock()
        mock_response.iter_bytes = MagicMock(side_effect=ConnectionError("network error"))
        mock_response.__enter__ = MagicMock(return_value=mock_response)
        mock_response.__exit__ = MagicMock(return_value=False)
        mocker.patch("downloader.httpx.stream", return_value=mock_response)

        # Do NOT pre-create the partial file — dest does not exist
        with pytest.raises(ConnectionError):
            _download_with_resume.__wrapped__(sample_rf_file, tmp_path / sample_rf_file.name)

        partial = tmp_path / "Empresas0.zip"
        assert partial.exists()
        assert partial.read_bytes() == b""
