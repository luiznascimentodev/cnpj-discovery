"""Testes para etl/extractor.py — sem I/O real da Receita Federal."""
import io
import zipfile
from pathlib import Path

import polars as pl
import pytest

from extractor import stream_zip_as_batches, _find_csv_entry, _parse_batch


# ─── Helpers ─────────────────────────────────────────────────────────────────

def make_zip_with_csv(tmp_path: Path, filename: str, content: bytes) -> Path:
    """Cria um arquivo ZIP sintético com um CSV dentro."""
    zip_path = tmp_path / "test.zip"
    with zipfile.ZipFile(zip_path, "w") as zf:
        zf.writestr(filename, content)
    return zip_path

COLUMNS = ["cnpj_basico", "razao_social", "capital_social"]

def make_csv_bytes(rows: list[list[str]]) -> bytes:
    """Gera bytes de CSV Latin-1 sem header, delimitado por ;."""
    lines = [";".join(row) + "\n" for row in rows]
    return "".join(lines).encode("latin-1")


# ─── _find_csv_entry ──────────────────────────────────────────────────────────

class TestFindCsvEntry:
    def test_finds_csv_extension(self, tmp_path):
        zip_path = make_zip_with_csv(tmp_path, "data.csv", b"test")
        with zipfile.ZipFile(zip_path) as zf:
            assert _find_csv_entry(zf, zip_path) == "data.csv"

    def test_finds_extensionless_file(self, tmp_path):
        zip_path = make_zip_with_csv(tmp_path, "K3241721Y0", b"test")
        with zipfile.ZipFile(zip_path) as zf:
            assert _find_csv_entry(zf, zip_path) == "K3241721Y0"

    def test_prefers_csv_over_extensionless(self, tmp_path):
        zip_path = tmp_path / "test.zip"
        with zipfile.ZipFile(zip_path, "w") as zf:
            zf.writestr("data.csv", b"csv_data")
            zf.writestr("NOEXT", b"noext_data")
        with zipfile.ZipFile(zip_path) as zf:
            result = _find_csv_entry(zf, zip_path)
            assert result == "data.csv"

    def test_raises_when_no_csv_or_extensionless(self, tmp_path):
        zip_path = tmp_path / "test.zip"
        with zipfile.ZipFile(zip_path, "w") as zf:
            zf.writestr("readme.txt", b"nothing here")
            zf.writestr("data.xml", b"<xml/>")
        with zipfile.ZipFile(zip_path) as zf:
            with pytest.raises(ValueError, match="No CSV or extensionless file"):
                _find_csv_entry(zf, zip_path)


# ─── _parse_batch ─────────────────────────────────────────────────────────────

class TestParseBatch:
    def test_returns_dataframe_with_correct_columns(self):
        lines = [b"00000001;EMPRESA A;1000,00\n", b"00000002;EMPRESA B;2000,00\n"]
        df = _parse_batch(lines, COLUMNS)
        assert list(df.columns) == COLUMNS

    def test_returns_correct_row_count(self):
        lines = [b"00000001;A;100\n", b"00000002;B;200\n", b"00000003;C;300\n"]
        df = _parse_batch(lines, COLUMNS)
        assert len(df) == 3

    def test_all_columns_are_utf8(self):
        lines = [b"00000001;EMPRESA;1000,00\n"]
        df = _parse_batch(lines, COLUMNS)
        for col in df.columns:
            assert df[col].dtype == pl.Utf8

    def test_handles_latin1_characters(self):
        # "ção" em Latin-1
        line = "00000001;CONSTRU\xe7\xc3O;500,00\n".encode("latin-1")
        df = _parse_batch([line], COLUMNS)
        assert len(df) == 1  # não travou

    def test_handles_single_line(self):
        lines = [b"12345678;EMPRESA UNICA;99,99\n"]
        df = _parse_batch(lines, COLUMNS)
        assert len(df) == 1
        assert df["cnpj_basico"][0] == "12345678"


# ─── stream_zip_as_batches ───────────────────────────────────────────────────

class TestStreamZipAsBatches:
    def test_streams_single_batch(self, tmp_path):
        rows = [[f"0000000{i}", f"EMPRESA {i}", f"{i*100},00"] for i in range(5)]
        csv_bytes = make_csv_bytes(rows)
        zip_path = make_zip_with_csv(tmp_path, "data.csv", csv_bytes)

        batches = list(stream_zip_as_batches(zip_path, COLUMNS, batch_size=100))
        assert len(batches) == 1
        assert len(batches[0]) == 5

    def test_streams_multiple_batches(self, tmp_path):
        rows = [[f"{i:08d}", f"EMPRESA {i}", f"{i},00"] for i in range(25)]
        csv_bytes = make_csv_bytes(rows)
        zip_path = make_zip_with_csv(tmp_path, "data.csv", csv_bytes)

        batches = list(stream_zip_as_batches(zip_path, COLUMNS, batch_size=10))
        assert len(batches) == 3  # 10 + 10 + 5
        total_rows = sum(len(b) for b in batches)
        assert total_rows == 25

    def test_each_batch_is_dataframe(self, tmp_path):
        rows = [[f"{i:08d}", f"EMPRESA {i}", "100,00"] for i in range(3)]
        csv_bytes = make_csv_bytes(rows)
        zip_path = make_zip_with_csv(tmp_path, "data.csv", csv_bytes)

        for batch in stream_zip_as_batches(zip_path, COLUMNS, batch_size=100):
            assert isinstance(batch, pl.DataFrame)

    def test_batch_has_correct_columns(self, tmp_path):
        rows = [["00000001", "EMPRESA A", "100,00"]]
        csv_bytes = make_csv_bytes(rows)
        zip_path = make_zip_with_csv(tmp_path, "data.csv", csv_bytes)

        batch = next(stream_zip_as_batches(zip_path, COLUMNS, batch_size=100))
        assert list(batch.columns) == COLUMNS

    def test_works_with_extensionless_file(self, tmp_path):
        rows = [["00000001", "EMPRESA", "500,00"]]
        csv_bytes = make_csv_bytes(rows)
        zip_path = make_zip_with_csv(tmp_path, "K3241721Y0", csv_bytes)

        batches = list(stream_zip_as_batches(zip_path, COLUMNS, batch_size=100))
        assert len(batches) == 1

    def test_raises_for_bad_zip(self, tmp_path):
        bad_zip = tmp_path / "bad.zip"
        bad_zip.write_bytes(b"not a zip file at all")

        with pytest.raises(zipfile.BadZipFile):
            list(stream_zip_as_batches(bad_zip, COLUMNS))

    def test_raises_when_no_csv_in_zip(self, tmp_path):
        zip_path = tmp_path / "empty.zip"
        with zipfile.ZipFile(zip_path, "w") as zf:
            zf.writestr("readme.txt", b"nothing")

        with pytest.raises(ValueError, match="No CSV or extensionless file"):
            list(stream_zip_as_batches(zip_path, COLUMNS))

    def test_empty_csv_yields_nothing(self, tmp_path):
        zip_path = make_zip_with_csv(tmp_path, "data.csv", b"")
        batches = list(stream_zip_as_batches(zip_path, COLUMNS, batch_size=10))
        # CSV vazio: nenhum batch (ou um batch com 0 rows, ambos OK)
        total_rows = sum(len(b) for b in batches)
        assert total_rows == 0

    def test_exact_batch_size_boundary(self, tmp_path):
        # 20 linhas com batch_size=10: deve gerar exatamente 2 batches
        rows = [[f"{i:08d}", f"E{i}", "100,00"] for i in range(20)]
        csv_bytes = make_csv_bytes(rows)
        zip_path = make_zip_with_csv(tmp_path, "data.csv", csv_bytes)

        batches = list(stream_zip_as_batches(zip_path, COLUMNS, batch_size=10))
        assert len(batches) == 2
        assert all(len(b) == 10 for b in batches)
