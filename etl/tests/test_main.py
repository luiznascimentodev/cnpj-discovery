"""Testes para etl/main.py — usa mocks para evitar I/O real."""
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import MagicMock, patch, call
import polars as pl
import pytest

from main import (
    _get_schema_for_file, _process_file, cmd_check_public_data, cmd_full_load,
    cmd_refresh_active_only_if_updated, cmd_update, cmd_status, main,
    _ensure_enough_free_space, _vacuum_analyze_all, _table_from_sql,
    _active_only_batch_filter, _partition_active_only_load, _validate_active_only_result,
)
from downloader import RFFile
from dataset_sources import DatasetFile, DatasetSnapshot


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

    def test_active_only_filter_keeps_only_active_estabelecimentos(self):
        df = pl.DataFrame({
            "cnpj_basico": ["00000001", "00000002", "00000003"],
            "situacao_cadastral": [2, 4, 8],
        })
        result = _active_only_batch_filter(df, "estabelecimentos")
        assert result["cnpj_basico"].to_list() == ["00000001"]

    def test_active_only_filter_ignores_other_tables(self):
        df = pl.DataFrame({"cnpj_basico": ["00000001", "00000002"]})
        result = _active_only_batch_filter(df, "empresas")
        assert result is df

    def test_process_file_filters_estabelecimentos_when_active_only(self):
        conn = self._make_mock_conn()
        rf = make_rf_file("Estabelecimentos0.zip")
        mock_df = pl.DataFrame({
            "cnpj_basico": ["00000001", "00000002"],
            "situacao_cadastral": [2, 4],
        })

        with patch("main.set_file_state"), \
             patch("main.stream_zip_as_batches", return_value=iter([mock_df])), \
             patch("main.disable_triggers"), \
             patch("main.enable_triggers"), \
             patch("main.bulk_copy", return_value=1) as mock_copy, \
             patch("main.TRANSFORM_MAP", {}):

            mock_zip_path = MagicMock(spec=Path)
            mock_zip_path.exists.return_value = False
            with patch("main.download_file", return_value=mock_zip_path):
                result = _process_file(conn, rf, mode="copy", active_only=True)

        assert result == 1
        loaded_df = mock_copy.call_args[0][1]
        assert loaded_df["cnpj_basico"].to_list() == ["00000001"]

    def test_process_file_uses_active_cnpj_join_for_dependent_tables(self):
        conn = self._make_mock_conn()
        rf = make_rf_file("Empresas0.zip")
        mock_df = pl.DataFrame({"cnpj_basico": ["00000001", "00000002"]})

        with patch("main.set_file_state"), \
             patch("main.stream_zip_as_batches", return_value=iter([mock_df])), \
             patch("main.disable_triggers"), \
             patch("main.enable_triggers"), \
             patch("main.bulk_copy_active_filtered", return_value=1) as mock_filtered, \
             patch("main.bulk_copy") as mock_copy, \
             patch("main.TRANSFORM_MAP", {}):

            mock_zip_path = MagicMock(spec=Path)
            mock_zip_path.exists.return_value = False
            with patch("main.download_file", return_value=mock_zip_path):
                result = _process_file(
                    conn,
                    rf,
                    mode="copy",
                    active_only=True,
                    filter_by_active_cnpj=True,
                )

        assert result == 1
        mock_filtered.assert_called_once()
        mock_copy.assert_not_called()


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
             patch("main._vacuum_analyze_all") as mock_vacuum, \
             patch("main.settings.etl_active_only", False):

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
             patch("main._vacuum_analyze_all"), \
             patch("main.settings.etl_active_only", False):

            mock_conn = MagicMock()
            mock_conn_ctx.return_value.__enter__ = MagicMock(return_value=mock_conn)
            mock_conn_ctx.return_value.__exit__ = MagicMock(return_value=False)

            # Should not raise even if one file fails
            cmd_full_load()

        assert mock_proc.call_count == 2

    def test_active_only_partition_orders_active_dependencies_after_estabelecimentos(self):
        bootstrap, establishments, active_dependents = _partition_active_only_load([
            make_rf_file("Empresas0.zip"),
            make_rf_file("CNAE.zip"),
            make_rf_file("Estabelecimentos0.zip"),
            make_rf_file("Socios0.zip"),
            make_rf_file("Simples.zip"),
        ])

        assert [f.name for f in bootstrap] == ["CNAE.zip"]
        assert [f.name for f in establishments] == ["Estabelecimentos0.zip"]
        assert [f.name for f in active_dependents] == [
            "Empresas0.zip",
            "Socios0.zip",
            "Simples.zip",
        ]


class TestCmdUpdate:
    def test_update_skips_up_to_date_files(self):
        rf_files = [make_rf_file("Empresas0.zip")]

        with patch("main.list_rf_files", return_value=rf_files), \
             patch("main.get_connection") as mock_conn_ctx, \
             patch("main.needs_update", return_value=False), \
             patch("main._process_file") as mock_proc, \
             patch("main.settings.etl_active_only", False):

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
             patch("main._process_file", return_value=100) as mock_proc, \
             patch("main.settings.etl_active_only", False):

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
             patch("main._process_file", side_effect=[Exception("fail"), 50]) as mock_proc, \
             patch("main.settings.etl_active_only", False):

            mock_conn = MagicMock()
            mock_conn_ctx.return_value.__enter__ = MagicMock(return_value=mock_conn)
            mock_conn_ctx.return_value.__exit__ = MagicMock(return_value=False)

            cmd_update()

        assert mock_proc.call_count == 2

    def test_update_is_disabled_in_active_only_mode(self):
        with patch("main.settings.etl_active_only", True):
            with pytest.raises(RuntimeError, match="ETL_ACTIVE_ONLY"):
                cmd_update()


class TestPublicDataCommands:
    def test_check_public_data_records_selected_snapshot(self):
        selected = DatasetSnapshot(
            source_name="rf_http_index",
            snapshot_key="2024-03",
            source_url="https://example.test/",
            files=[DatasetFile("Empresas0.zip", "https://example.test/Empresas0.zip", 123)],
        )
        catalog = DatasetSnapshot(
            source_name="dados_gov_catalog",
            snapshot_key="2024-03-01",
            source_url="https://dados.gov.br/",
            files=[DatasetFile("catalog.html", "https://dados.gov.br/", 50)],
        )
        with (
            patch("main.discover_dataset_snapshots", return_value=[selected, catalog]),
            patch("main.choose_load_snapshot", return_value=selected),
            patch("main.get_connection") as mock_conn_ctx,
            patch("main.record_snapshot", return_value=(1, "pending_load")) as record,
        ):
            mock_conn = MagicMock()
            mock_conn_ctx.return_value.__enter__ = MagicMock(return_value=mock_conn)
            mock_conn_ctx.return_value.__exit__ = MagicMock(return_value=False)
            cmd_check_public_data()

        assert record.call_args_list[0].kwargs["selected"] is True
        assert record.call_args_list[1].kwargs["selected"] is False

    def test_check_public_data_raises_when_sources_empty(self):
        with patch("main.discover_dataset_snapshots", return_value=[]):
            with pytest.raises(RuntimeError, match="No public"):
                cmd_check_public_data()

    def test_ensure_enough_free_space_accepts_threshold(self, tmp_path):
        usage = MagicMock(free=100 * 1024**3)
        with (
            patch("main.settings.etl_data_dir", str(tmp_path / "data")),
            patch("main.settings.etl_min_free_gb", 70),
            patch("main.shutil.disk_usage", return_value=usage),
        ):
            _ensure_enough_free_space()

    def test_ensure_enough_free_space_rejects_low_disk(self, tmp_path):
        usage = MagicMock(free=10 * 1024**3)
        with (
            patch("main.settings.etl_data_dir", str(tmp_path)),
            patch("main.settings.etl_min_free_gb", 70),
            patch("main.shutil.disk_usage", return_value=usage),
        ):
            with pytest.raises(RuntimeError, match="Insufficient"):
                _ensure_enough_free_space()

    def test_validate_active_only_result_passes_when_zero_inactive(self):
        mock_conn = MagicMock()
        mock_cur = MagicMock()
        mock_cur.fetchone.return_value = (0,)
        mock_conn.cursor.return_value.__enter__ = MagicMock(return_value=mock_cur)
        mock_conn.cursor.return_value.__exit__ = MagicMock(return_value=False)
        with patch("main.settings.etl_active_only", True), patch("main.get_connection") as ctx:
            ctx.return_value.__enter__ = MagicMock(return_value=mock_conn)
            ctx.return_value.__exit__ = MagicMock(return_value=False)
            _validate_active_only_result()

    def test_validate_active_only_result_raises_on_inactive(self):
        mock_conn = MagicMock()
        mock_cur = MagicMock()
        mock_cur.fetchone.return_value = (1,)
        mock_conn.cursor.return_value.__enter__ = MagicMock(return_value=mock_cur)
        mock_conn.cursor.return_value.__exit__ = MagicMock(return_value=False)
        with patch("main.settings.etl_active_only", True), patch("main.get_connection") as ctx:
            ctx.return_value.__enter__ = MagicMock(return_value=mock_conn)
            ctx.return_value.__exit__ = MagicMock(return_value=False)
            with pytest.raises(RuntimeError, match="Active-only"):
                _validate_active_only_result()

    def test_refresh_skips_without_lock(self):
        with patch("main.get_connection") as ctx, patch("main.try_refresh_lock", return_value=False):
            mock_conn = MagicMock()
            ctx.return_value.__enter__ = MagicMock(return_value=mock_conn)
            ctx.return_value.__exit__ = MagicMock(return_value=False)
            cmd_refresh_active_only_if_updated()

    def test_refresh_leaves_pending_when_auto_load_disabled(self):
        with (
            patch("main.get_connection") as ctx,
            patch("main.try_refresh_lock", return_value=True),
            patch("main.get_pending_snapshot", return_value=(10, "2024-03", "rf_http_index")),
            patch("main.settings.etl_auto_load_public_data", False),
            patch("main.release_refresh_lock") as release,
        ):
            mock_conn = MagicMock()
            ctx.return_value.__enter__ = MagicMock(return_value=mock_conn)
            ctx.return_value.__exit__ = MagicMock(return_value=False)
            cmd_refresh_active_only_if_updated()

        release.assert_called_once()

    def test_refresh_runs_full_load_and_marks_loaded(self):
        with (
            patch("main.get_connection") as ctx,
            patch("main.try_refresh_lock", return_value=True),
            patch("main.get_pending_snapshot", return_value=(10, "2024-03", "rf_http_index")),
            patch("main.settings.etl_auto_load_public_data", True),
            patch("main._ensure_enough_free_space"),
            patch("main.cmd_full_load"),
            patch("main._validate_active_only_result"),
            patch("main.mark_snapshot_loaded") as loaded,
            patch("main.release_refresh_lock"),
        ):
            mock_conn = MagicMock()
            ctx.return_value.__enter__ = MagicMock(return_value=mock_conn)
            ctx.return_value.__exit__ = MagicMock(return_value=False)
            cmd_refresh_active_only_if_updated()

        loaded.assert_called_once()

    def test_refresh_marks_failed_on_error(self):
        with (
            patch("main.get_connection") as ctx,
            patch("main.try_refresh_lock", return_value=True),
            patch("main.get_pending_snapshot", return_value=(10, "2024-03", "rf_http_index")),
            patch("main.settings.etl_auto_load_public_data", True),
            patch("main._ensure_enough_free_space", side_effect=RuntimeError("disk")),
            patch("main.mark_snapshot_failed") as failed,
            patch("main.release_refresh_lock"),
        ):
            mock_conn = MagicMock()
            ctx.return_value.__enter__ = MagicMock(return_value=mock_conn)
            ctx.return_value.__exit__ = MagicMock(return_value=False)
            with pytest.raises(RuntimeError, match="disk"):
                cmd_refresh_active_only_if_updated()

        failed.assert_called_once()


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

    def test_main_check_public_data(self):
        with patch("main.cmd_check_public_data") as mock_cmd, \
             patch("sys.argv", ["main.py", "check-public-data"]):
            main()
        mock_cmd.assert_called_once()

    def test_main_refresh_active_only_if_updated(self):
        with patch("main.cmd_refresh_active_only_if_updated") as mock_cmd, \
             patch("sys.argv", ["main.py", "refresh-active-only-if-updated"]):
            main()
        mock_cmd.assert_called_once()
