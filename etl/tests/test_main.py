"""Testes para etl/main.py — usa mocks para evitar I/O real."""
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import MagicMock, patch, call
import polars as pl
import pytest

from main import (
    _get_schema_for_file, _process_file, cmd_full_load, cmd_update, cmd_status, main,
    _vacuum_analyze_all, _table_from_sql,
)
from downloader import RFFile


NOW = datetime(2024, 1, 1, tzinfo=timezone.utc)


def make_rf_file(name: str) -> RFFile:
    return RFFile(name=name, last_modified=NOW, size=1024)


class TestGetSchemaForFile:
    def test_recognizes_empresas(self):
        schema = _get_schema_for_file("Empresas0.zip")
        assert schema is not None
        assert schema.table == "empresas"

    def test_recognizes_estabelecimentos(self):
        schema = _get_schema_for_file("Estabelecimentos3.zip")
        assert schema is not None
        assert schema.table == "estabelecimentos"

    def test_recognizes_socios(self):
        schema = _get_schema_for_file("Socios0.zip")
        assert schema is not None
        assert schema.table == "socios"

    def test_recognizes_simples(self):
        schema = _get_schema_for_file("Simples.zip")
        assert schema is not None
        assert schema.table == "simples"

    def test_recognizes_cnae(self):
        schema = _get_schema_for_file("CNAE.zip")
        assert schema is not None
        assert schema.table == "cnaes"

    def test_recognizes_municipios(self):
        schema = _get_schema_for_file("Municipios.zip")
        assert schema is not None

    def test_returns_none_for_unknown(self):
        schema = _get_schema_for_file("Unknown.zip")
        assert schema is None


class TestCmdStatus:
    def test_prints_no_state_message(self, capsys):
        with patch("main.get_connection") as mock_conn_ctx:
            mock_conn = MagicMock()
            mock_conn_ctx.return_value.__enter__ = MagicMock(return_value=mock_conn)
            mock_conn_ctx.return_value.__exit__ = MagicMock(return_value=False)
            with patch("main.get_all_states", return_value=[]):
                cmd_status()
        captured = capsys.readouterr()
        assert "full-load" in captured.out

    def test_prints_states_table(self, capsys):
        from state import ETLFileState
        mock_state = ETLFileState(
            arquivo="Empresas0.zip",
            status="done",
            last_modified=NOW,
            loaded_at=NOW,
            rows_processed=7_000_000,
        )
        with patch("main.get_connection") as mock_conn_ctx:
            mock_conn = MagicMock()
            mock_conn_ctx.return_value.__enter__ = MagicMock(return_value=mock_conn)
            mock_conn_ctx.return_value.__exit__ = MagicMock(return_value=False)
            with patch("main.get_all_states", return_value=[mock_state]):
                cmd_status()
        captured = capsys.readouterr()
        assert "Empresas0.zip" in captured.out
        assert "done" in captured.out

    def test_prints_na_for_null_loaded_at(self, capsys):
        from state import ETLFileState
        mock_state = ETLFileState(
            arquivo="Empresas0.zip",
            status="done",
            last_modified=NOW,
            loaded_at=None,
            rows_processed=0,
        )
        with patch("main.get_connection") as mock_conn_ctx:
            mock_conn = MagicMock()
            mock_conn_ctx.return_value.__enter__ = MagicMock(return_value=mock_conn)
            mock_conn_ctx.return_value.__exit__ = MagicMock(return_value=False)
            with patch("main.get_all_states", return_value=[mock_state]):
                cmd_status()
        captured = capsys.readouterr()
        assert "N/A" in captured.out


class TestProcessFile:
    def _make_mock_conn(self):
        return MagicMock()

    def test_skips_unknown_file(self):
        conn = self._make_mock_conn()
        rf = make_rf_file("Unknown999.zip")
        result = _process_file(conn, rf, mode="copy")
        assert result == 0

    def test_copy_mode_success(self):
        conn = self._make_mock_conn()
        rf = make_rf_file("Empresas0.zip")
        mock_df = pl.DataFrame({"cnpj_basico": ["12345678"]})

        with patch("main.set_file_state") as mock_set_state, \
             patch("main.download_file", return_value=Path("/tmp/test.zip")) as mock_dl, \
             patch("main.stream_zip_as_batches", return_value=iter([mock_df])) as mock_stream, \
             patch("main.disable_triggers") as mock_dis, \
             patch("main.enable_triggers") as mock_en, \
             patch("main.bulk_copy", return_value=1) as mock_copy, \
             patch("main.TRANSFORM_MAP", {}):

            # Make zip_path.exists() return False so unlink is not called
            mock_zip_path = MagicMock(spec=Path)
            mock_zip_path.exists.return_value = False
            mock_dl.return_value = mock_zip_path

            result = _process_file(conn, rf, mode="copy")

        assert result == 1
        mock_dis.assert_called_once()
        mock_en.assert_called_once()
        mock_copy.assert_called_once()

    def test_copy_mode_deletes_zip(self):
        conn = self._make_mock_conn()
        rf = make_rf_file("Empresas0.zip")
        mock_df = pl.DataFrame({"cnpj_basico": ["12345678"]})

        with patch("main.set_file_state"), \
             patch("main.stream_zip_as_batches", return_value=iter([mock_df])), \
             patch("main.disable_triggers"), \
             patch("main.enable_triggers"), \
             patch("main.bulk_copy", return_value=1), \
             patch("main.TRANSFORM_MAP", {}):

            mock_zip_path = MagicMock(spec=Path)
            mock_zip_path.exists.return_value = True
            with patch("main.download_file", return_value=mock_zip_path):
                _process_file(conn, rf, mode="copy")

        mock_zip_path.unlink.assert_called_once()

    def test_upsert_mode_success(self):
        conn = self._make_mock_conn()
        rf = make_rf_file("Empresas0.zip")
        mock_df = pl.DataFrame({"cnpj_basico": ["12345678"]})

        with patch("main.set_file_state"), \
             patch("main.stream_zip_as_batches", return_value=iter([mock_df])), \
             patch("main.upsert", return_value=1) as mock_upsert, \
             patch("main.TRANSFORM_MAP", {}):

            mock_zip_path = MagicMock(spec=Path)
            mock_zip_path.exists.return_value = False
            with patch("main.download_file", return_value=mock_zip_path):
                result = _process_file(conn, rf, mode="upsert")

        assert result == 1
        mock_upsert.assert_called_once()

    def test_applies_transform_fn(self):
        conn = self._make_mock_conn()
        rf = make_rf_file("Empresas0.zip")
        mock_df = pl.DataFrame({"cnpj_basico": ["12345678"]})
        transformed_df = pl.DataFrame({"cnpj_basico": ["00012345678"]})
        mock_transform = MagicMock(return_value=transformed_df)

        with patch("main.set_file_state"), \
             patch("main.stream_zip_as_batches", return_value=iter([mock_df])), \
             patch("main.disable_triggers"), \
             patch("main.enable_triggers"), \
             patch("main.bulk_copy", return_value=1), \
             patch("main.TRANSFORM_MAP", {"empresas": mock_transform}):

            mock_zip_path = MagicMock(spec=Path)
            mock_zip_path.exists.return_value = False
            with patch("main.download_file", return_value=mock_zip_path):
                _process_file(conn, rf, mode="copy")

        mock_transform.assert_called_once_with(mock_df)

    def test_download_error_sets_error_state(self):
        conn = self._make_mock_conn()
        rf = make_rf_file("Empresas0.zip")

        with patch("main.set_file_state") as mock_set_state, \
             patch("main.download_file", side_effect=Exception("network error")):
            with pytest.raises(Exception, match="network error"):
                _process_file(conn, rf, mode="copy")

        # Should have been called with "downloading" then "error"
        calls = mock_set_state.call_args_list
        statuses = [c[0][2] for c in calls]
        assert "error" in statuses

    def test_processing_error_in_copy_mode_enables_triggers(self):
        conn = self._make_mock_conn()
        rf = make_rf_file("Empresas0.zip")
        mock_df = pl.DataFrame({"cnpj_basico": ["12345678"]})

        with patch("main.set_file_state"), \
             patch("main.stream_zip_as_batches", return_value=iter([mock_df])), \
             patch("main.disable_triggers") as mock_dis, \
             patch("main.enable_triggers") as mock_en, \
             patch("main.bulk_copy", side_effect=Exception("db error")), \
             patch("main.TRANSFORM_MAP", {}):

            mock_zip_path = MagicMock(spec=Path)
            mock_zip_path.exists.return_value = False
            with patch("main.download_file", return_value=mock_zip_path):
                with pytest.raises(Exception, match="db error"):
                    _process_file(conn, rf, mode="copy")

        mock_dis.assert_called_once()
        mock_en.assert_called_once()

    def test_processing_error_deletes_zip(self):
        conn = self._make_mock_conn()
        rf = make_rf_file("Empresas0.zip")
        mock_df = pl.DataFrame({"cnpj_basico": ["12345678"]})

        with patch("main.set_file_state"), \
             patch("main.stream_zip_as_batches", return_value=iter([mock_df])), \
             patch("main.disable_triggers"), \
             patch("main.enable_triggers"), \
             patch("main.bulk_copy", side_effect=Exception("db error")), \
             patch("main.TRANSFORM_MAP", {}):

            mock_zip_path = MagicMock(spec=Path)
            mock_zip_path.exists.return_value = True
            with patch("main.download_file", return_value=mock_zip_path):
                with pytest.raises(Exception):
                    _process_file(conn, rf, mode="copy")

        mock_zip_path.unlink.assert_called_once()


class TestCmdFullLoad:
    def test_full_load_processes_all_files(self):
        rf_files = [make_rf_file("Empresas0.zip"), make_rf_file("Socios0.zip")]

        with patch("main.list_rf_files", return_value=rf_files), \
             patch("main.get_connection") as mock_conn_ctx, \
             patch("main.drop_managed_indexes") as mock_drop, \
             patch("main.create_managed_indexes") as mock_create, \
             patch("main.download_file", return_value=Path("/tmp/fake.zip")), \
             patch("main.set_file_state"), \
             patch("main._process_file", return_value=100) as mock_proc, \
             patch("main._vacuum_analyze_all") as mock_vacuum:

            mock_conn = MagicMock()
            mock_conn_ctx.return_value.__enter__ = MagicMock(return_value=mock_conn)
            mock_conn_ctx.return_value.__exit__ = MagicMock(return_value=False)

            cmd_full_load()

        mock_drop.assert_called_once()
        mock_create.assert_called_once()
        mock_vacuum.assert_called_once()
        assert mock_proc.call_count == 2

    def test_full_load_continues_on_error(self):
        rf_files = [make_rf_file("Empresas0.zip"), make_rf_file("Socios0.zip")]

        with patch("main.list_rf_files", return_value=rf_files), \
             patch("main.get_connection") as mock_conn_ctx, \
             patch("main.drop_managed_indexes"), \
             patch("main.create_managed_indexes"), \
             patch("main.download_file", return_value=Path("/tmp/fake.zip")), \
             patch("main.set_file_state"), \
             patch("main._process_file", side_effect=[Exception("fail"), 50]) as mock_proc, \
             patch("main._vacuum_analyze_all"):

            mock_conn = MagicMock()
            mock_conn_ctx.return_value.__enter__ = MagicMock(return_value=mock_conn)
            mock_conn_ctx.return_value.__exit__ = MagicMock(return_value=False)

            # Should not raise even if one file fails
            cmd_full_load()

        assert mock_proc.call_count == 2


class TestCmdUpdate:
    def test_update_skips_up_to_date_files(self):
        rf_files = [make_rf_file("Empresas0.zip")]

        with patch("main.list_rf_files", return_value=rf_files), \
             patch("main.get_connection") as mock_conn_ctx, \
             patch("main.needs_update", return_value=False), \
             patch("main._process_file") as mock_proc:

            mock_conn = MagicMock()
            mock_conn_ctx.return_value.__enter__ = MagicMock(return_value=mock_conn)
            mock_conn_ctx.return_value.__exit__ = MagicMock(return_value=False)

            cmd_update()

        mock_proc.assert_not_called()

    def test_update_processes_new_files(self):
        rf_files = [make_rf_file("Empresas0.zip"), make_rf_file("Socios0.zip")]

        with patch("main.list_rf_files", return_value=rf_files), \
             patch("main.get_connection") as mock_conn_ctx, \
             patch("main.needs_update", return_value=True), \
             patch("main._process_file", return_value=100) as mock_proc:

            mock_conn = MagicMock()
            mock_conn_ctx.return_value.__enter__ = MagicMock(return_value=mock_conn)
            mock_conn_ctx.return_value.__exit__ = MagicMock(return_value=False)

            cmd_update()

        assert mock_proc.call_count == 2

    def test_update_continues_on_error(self):
        rf_files = [make_rf_file("Empresas0.zip"), make_rf_file("Socios0.zip")]

        with patch("main.list_rf_files", return_value=rf_files), \
             patch("main.get_connection") as mock_conn_ctx, \
             patch("main.needs_update", return_value=True), \
             patch("main._process_file", side_effect=[Exception("fail"), 50]) as mock_proc:

            mock_conn = MagicMock()
            mock_conn_ctx.return_value.__enter__ = MagicMock(return_value=mock_conn)
            mock_conn_ctx.return_value.__exit__ = MagicMock(return_value=False)

            cmd_update()

        assert mock_proc.call_count == 2


class TestTableFromSql:
    def test_extracts_plain_table(self):
        sql = "CREATE INDEX CONCURRENTLY IF NOT EXISTS idx ON estabelecimentos (uf)"
        assert _table_from_sql(sql) == "estabelecimentos"

    def test_extracts_table_with_gin(self):
        sql = ("CREATE INDEX CONCURRENTLY IF NOT EXISTS idx "
               "ON empresas USING GIN (to_tsvector('portuguese', razao_social))")
        assert _table_from_sql(sql) == "empresas"

    def test_extracts_table_with_where(self):
        sql = ("CREATE INDEX CONCURRENTLY IF NOT EXISTS idx "
               "ON estabelecimentos (uf, cnpj_basico, cnpj_ordem) WHERE situacao_cadastral = 2")
        assert _table_from_sql(sql) == "estabelecimentos"


class TestVacuumAnalyzeAll:
    def test_runs_vacuum_on_all_tables(self):
        mock_conn = MagicMock()
        mock_cur = MagicMock()
        mock_conn.cursor.return_value.__enter__ = MagicMock(return_value=mock_cur)
        mock_conn.cursor.return_value.__exit__ = MagicMock(return_value=False)

        with patch("main.psycopg2.connect", return_value=mock_conn):
            _vacuum_analyze_all()

        # Deve ter chamado VACUUM ANALYZE para cada tabela única
        calls_sql = [c[0][0] for c in mock_cur.execute.call_args_list]
        vacuum_calls = [s for s in calls_sql if "VACUUM ANALYZE" in s]
        assert len(vacuum_calls) >= 4  # empresas, estabelecimentos, simples, socios

    def test_sets_autocommit(self):
        mock_conn = MagicMock()
        mock_cur = MagicMock()
        mock_conn.cursor.return_value.__enter__ = MagicMock(return_value=mock_cur)
        mock_conn.cursor.return_value.__exit__ = MagicMock(return_value=False)

        with patch("main.psycopg2.connect", return_value=mock_conn):
            _vacuum_analyze_all()

        assert mock_conn.autocommit is True

    def test_closes_connection(self):
        mock_conn = MagicMock()
        mock_cur = MagicMock()
        mock_conn.cursor.return_value.__enter__ = MagicMock(return_value=mock_cur)
        mock_conn.cursor.return_value.__exit__ = MagicMock(return_value=False)

        with patch("main.psycopg2.connect", return_value=mock_conn):
            _vacuum_analyze_all()

        mock_conn.close.assert_called_once()


class TestMain:
    def test_main_full_load(self):
        with patch("main.cmd_full_load") as mock_cmd, \
             patch("sys.argv", ["main.py", "full-load"]):
            main()
        mock_cmd.assert_called_once()

    def test_main_update(self):
        with patch("main.cmd_update") as mock_cmd, \
             patch("sys.argv", ["main.py", "update"]):
            main()
        mock_cmd.assert_called_once()

    def test_main_status(self):
        with patch("main.cmd_status") as mock_cmd, \
             patch("sys.argv", ["main.py", "status"]):
            main()
        mock_cmd.assert_called_once()
