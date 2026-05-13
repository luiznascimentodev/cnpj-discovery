import hashlib
import re
from dataclasses import dataclass
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from html.parser import HTMLParser
from urllib.parse import urljoin

import httpx

from config import settings
from downloader import RFFile, list_rf_files

_SNAPSHOT_RE = re.compile(r"^\d{4}-\d{2}/?$")
_ZIP_RE = re.compile(r"\.zip$", re.IGNORECASE)
_INDEX_ROW_RE = re.compile(
    r'href="(?P<href>[^"]+)">\s*(?P<label>[^<]+)</a>\s*'
    r'(?P<modified>\d{4}-\d{2}-\d{2}\s+\d{2}:\d{2})?\s*'
    r'(?P<size>[0-9.]+[KMGTP]?)?',
    re.IGNORECASE,
)


@dataclass(frozen=True)
class DatasetFile:
    file_name: str
    url: str
    size_bytes: int
    last_modified: datetime | None = None
    etag: str | None = None
    sha256: str | None = None


@dataclass(frozen=True)
class DatasetSnapshot:
    source_name: str
    snapshot_key: str
    source_url: str
    files: list[DatasetFile]

    @property
    def file_count(self) -> int:
        return len(self.files)

    @property
    def total_size_bytes(self) -> int:
        return sum(file.size_bytes for file in self.files)

    @property
    def last_modified_max(self) -> datetime | None:
        values = [file.last_modified for file in self.files if file.last_modified]
        return max(values) if values else None

    @property
    def manifest_hash(self) -> str:
        parts = [
            f"{file.file_name}:{file.size_bytes}:{file.last_modified}:{file.etag}"
            for file in sorted(self.files, key=lambda item: item.file_name)
        ]
        return hashlib.sha256("|".join(parts).encode("utf-8")).hexdigest()


class _HrefParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.hrefs: list[str] = []

    def handle_starttag(self, tag: str, attrs) -> None:
        if tag.lower() != "a":
            return
        for key, value in attrs:
            if key.lower() == "href" and value:
                self.hrefs.append(value)


def _parse_size(value: str | None) -> int:
    if not value or value == "-":
        return 0
    units = {"K": 1024, "M": 1024**2, "G": 1024**3, "T": 1024**4, "P": 1024**5}
    suffix = value[-1].upper()
    if suffix in units:
        return int(float(value[:-1]) * units[suffix])
    return int(float(value))


def _parse_index_datetime(value: str | None) -> datetime | None:
    if not value:
        return None
    return datetime.strptime(value, "%Y-%m-%d %H:%M").replace(tzinfo=timezone.utc)


def parse_http_index(html: str, *, base_url: str, snapshot_key: str) -> DatasetSnapshot:
    files: list[DatasetFile] = []
    for match in _INDEX_ROW_RE.finditer(html):
        href = match.group("href")
        label = match.group("label").strip()
        if not _ZIP_RE.search(href) and not _ZIP_RE.search(label):
            continue
        file_name = href.rstrip("/").split("/")[-1]
        files.append(
            DatasetFile(
                file_name=file_name,
                url=urljoin(base_url, href),
                size_bytes=_parse_size(match.group("size")),
                last_modified=_parse_index_datetime(match.group("modified")),
            )
        )
    return DatasetSnapshot(
        source_name="rf_http_index",
        snapshot_key=snapshot_key,
        source_url=base_url,
        files=sorted(files, key=lambda item: item.file_name),
    )


def parse_snapshot_links(html: str) -> list[str]:
    parser = _HrefParser()
    parser.feed(html)
    snapshots = [href.rstrip("/") for href in parser.hrefs if _SNAPSHOT_RE.match(href)]
    return sorted(set(snapshots))


def discover_rf_http_index() -> DatasetSnapshot | None:
    with httpx.Client(timeout=30, follow_redirects=True) as client:
        root = client.get(settings.rf_http_index_url)
        root.raise_for_status()
        snapshots = parse_snapshot_links(root.text)
        if not snapshots:
            return parse_http_index(
                root.text,
                base_url=settings.rf_http_index_url,
                snapshot_key="root",
            )
        snapshot_key = snapshots[-1]
        snapshot_url = urljoin(settings.rf_http_index_url, f"{snapshot_key}/")
        response = client.get(snapshot_url)
        response.raise_for_status()
        return parse_http_index(response.text, base_url=snapshot_url, snapshot_key=snapshot_key)


def _snapshot_key_from_rf_files(files: list[RFFile]) -> str:
    paths = [file.url_path or "" for file in files]
    for path in paths:
        for part in path.split("/"):
            if _SNAPSHOT_RE.match(part):
                return part.rstrip("/")
    latest = max((file.last_modified for file in files), default=None)
    return latest.strftime("%Y-%m") if latest else "unknown"


def discover_rf_webdav() -> DatasetSnapshot:
    files = list_rf_files()
    dataset_files = [
        DatasetFile(
            file_name=file.name,
            url=file.url_path or file.name,
            size_bytes=file.size,
            last_modified=file.last_modified,
        )
        for file in files
    ]
    return DatasetSnapshot(
        source_name="rf_webdav",
        snapshot_key=_snapshot_key_from_rf_files(files),
        source_url=settings.rf_webdav_base,
        files=dataset_files,
    )


def discover_dados_gov_catalog() -> DatasetSnapshot:
    with httpx.Client(timeout=30, follow_redirects=True) as client:
        response = client.get(settings.dados_gov_cnpj_url)
        response.raise_for_status()
        last_modified = response.headers.get("last-modified")
        parsed = parsedate_to_datetime(last_modified) if last_modified else None
        etag = response.headers.get("etag")
        html_hash = hashlib.sha256(response.text.encode("utf-8")).hexdigest()
    file = DatasetFile(
        file_name="dados-gov-cnpj-catalog.html",
        url=settings.dados_gov_cnpj_url,
        size_bytes=len(response.text.encode("utf-8")),
        last_modified=parsed,
        etag=etag or html_hash,
    )
    key_date = parsed or datetime.now(timezone.utc)
    return DatasetSnapshot(
        source_name="dados_gov_catalog",
        snapshot_key=key_date.strftime("%Y-%m-%d"),
        source_url=settings.dados_gov_cnpj_url,
        files=[file],
    )


def discover_dataset_snapshots() -> list[DatasetSnapshot]:
    snapshots: list[DatasetSnapshot] = []
    for discover in (discover_rf_webdav, discover_rf_http_index, discover_dados_gov_catalog):
        snapshot = discover()
        if snapshot and snapshot.file_count > 0:
            snapshots.append(snapshot)
    return snapshots


def choose_load_snapshot(snapshots: list[DatasetSnapshot]) -> DatasetSnapshot | None:
    bulk_sources = [snapshot for snapshot in snapshots if snapshot.source_name in {"rf_webdav", "rf_http_index"}]
    if not bulk_sources:
        return None
    return max(bulk_sources, key=lambda item: (item.snapshot_key, item.file_count, item.total_size_bytes))
