"""
Download de arquivos da Receita Federal via WebDAV (Nextcloud share público).

O certificado SSL da RF usa ICP-Brasil (não reconhecido por certifi),
então usamos verify=False nas requisições.
"""
import io
import re
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from datetime import datetime
from email.utils import parsedate_to_datetime
from pathlib import Path
from urllib.parse import unquote

import httpx
from loguru import logger
from tenacity import retry, stop_after_attempt, wait_exponential, before_sleep_log
import logging

from config import settings

_DAV_NS = "DAV:"
_CNPJ_ROOT_PATH = "Dados/Cadastros/CNPJ/"
_SNAPSHOT_RE = re.compile(r"^\d{4}-\d{2}$")


@dataclass(frozen=True)
class RFFile:
    name: str
    last_modified: datetime
    size: int
    url_path: str | None = None


def list_rf_files() -> list[RFFile]:
    """
    Lista arquivos disponíveis via WebDAV PROPFIND.
    Retorna apenas arquivos .zip (ignora diretórios).
    """
    with httpx.Client(verify=False, timeout=30) as client:
        resp = _propfind(client, settings.rf_webdav_base)
        files = _parse_propfind_response(resp.text)

        if files:
            return files

        resp = _propfind(client, _webdav_url(_CNPJ_ROOT_PATH))
        snapshot_path = _latest_cnpj_snapshot_path(resp.text)
        if snapshot_path is None:
            return []

        logger.info(f"Using latest CNPJ snapshot folder: {snapshot_path}")
        resp = _propfind(client, _webdav_url(snapshot_path))
        return _parse_propfind_response(resp.text)


def _propfind(client: httpx.Client, url: str) -> httpx.Response:
    resp = client.request(
        "PROPFIND",
        url,
        auth=(settings.rf_share_token, ""),
        headers={"Depth": "1"},
    )
    resp.raise_for_status()
    return resp


def _parse_propfind_response(xml_text: str) -> list[RFFile]:
    """Parse XML PROPFIND response e extrai metadados dos arquivos ZIP."""
    root = ET.fromstring(xml_text)
    files = []
    for response in root.findall(f"{{{_DAV_NS}}}response"):
        href = response.findtext(f"{{{_DAV_NS}}}href", default="")
        name = href.rstrip("/").split("/")[-1]
        if not name.lower().endswith(".zip"):
            continue
        props = response.find(f".//{{{_DAV_NS}}}prop")
        if props is None:
            continue
        lm_str = props.findtext(f"{{{_DAV_NS}}}getlastmodified", default="")
        size_str = props.findtext(f"{{{_DAV_NS}}}getcontentlength", default="0")
        try:
            last_modified = parsedate_to_datetime(lm_str) if lm_str else datetime.min
        except Exception:
            last_modified = datetime.min
        files.append(RFFile(
            name=name,
            last_modified=last_modified,
            size=int(size_str),
            url_path=_webdav_path_from_href(href),
        ))
    return sorted(files, key=lambda f: f.name)


def _latest_cnpj_snapshot_path(xml_text: str) -> str | None:
    root = ET.fromstring(xml_text)
    snapshots = []

    for response in root.findall(f"{{{_DAV_NS}}}response"):
        href = response.findtext(f"{{{_DAV_NS}}}href", default="")
        path = _webdav_path_from_href(href)

        if not path.startswith(_CNPJ_ROOT_PATH):
            continue

        snapshot = path[len(_CNPJ_ROOT_PATH):].strip("/")
        if _SNAPSHOT_RE.match(snapshot):
            snapshots.append(snapshot)

    if not snapshots:
        return None

    return f"{_CNPJ_ROOT_PATH}{max(snapshots)}/"


def _webdav_path_from_href(href: str) -> str:
    path = unquote(href.lstrip("/"))
    marker = "public.php/webdav/"
    if marker in path:
        return path.split(marker, 1)[1]
    return path


def _webdav_url(path: str) -> str:
    return settings.rf_webdav_base.rstrip("/") + "/" + path.lstrip("/")


@retry(
    stop=stop_after_attempt(5),
    wait=wait_exponential(multiplier=1, min=2, max=60),
    before_sleep=before_sleep_log(logger, logging.WARNING),
    reraise=True,
)
def download_file(rf_file: RFFile, dest_dir: str) -> Path:
    """
    Faz download de um arquivo ZIP via streaming httpx com retry exponencial.

    - Usa chunks de 1 MB para não estourar a RAM
    - Apaga arquivo parcial em caso de erro
    - Retry automático até 5 tentativas
    """
    dest_dir_path = Path(dest_dir)
    dest_dir_path.mkdir(parents=True, exist_ok=True)
    dest = dest_dir_path / rf_file.name
    url = _webdav_url(rf_file.url_path or rf_file.name)

    logger.info(
        f"Downloading {rf_file.name} "
        f"({rf_file.size / 1_000_000:.1f} MB)..."
    )

    try:
        with httpx.stream(
            "GET", url,
            auth=(settings.rf_share_token, ""),
            verify=False,
            timeout=None,
            follow_redirects=True,
        ) as response:
            response.raise_for_status()
            with open(dest, "wb") as f:
                for chunk in response.iter_bytes(chunk_size=1_024 * 1_024):
                    f.write(chunk)
    except Exception:
        if dest.exists():
            dest.unlink()
        raise

    logger.success(f"Downloaded {rf_file.name} → {dest} ({dest.stat().st_size} bytes)")
    return dest
