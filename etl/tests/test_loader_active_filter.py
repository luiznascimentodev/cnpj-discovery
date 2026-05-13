from unittest.mock import MagicMock, patch

import polars as pl
import pytest

from loader import (
    bulk_copy_active_filtered,
    drop_active_cnpj_filter,
    rebuild_active_cnpj_filter,
)


def _mock_conn():
    conn = MagicMock()
    cur = MagicMock()
    conn.cursor.return_value.__enter__ = MagicMock(return_value=cur)
    conn.cursor.return_value.__exit__ = MagicMock(return_value=False)
    return conn, cur


def test_rebuild_active_cnpj_filter_returns_count_and_commits():
    conn, cur = _mock_conn()
    cur.fetchone.return_value = [123]

    result = rebuild_active_cnpj_filter(conn)

    assert result == 123
    assert conn.commit.called
    calls = [c[0][0] for c in cur.execute.call_args_list]
    assert any("CREATE UNLOGGED TABLE etl_active_cnpjs" in sql for sql in calls)
    assert any("WHERE situacao_cadastral = 2" in sql for sql in calls)


def test_drop_active_cnpj_filter_commits():
    conn, cur = _mock_conn()

    drop_active_cnpj_filter(conn)

    cur.execute.assert_called_once_with("DROP TABLE IF EXISTS etl_active_cnpjs")
    conn.commit.assert_called_once()


def test_active_filtered_copy_returns_zero_for_empty_df():
    conn, _ = _mock_conn()
    df = pl.DataFrame({"cnpj_basico": []}, schema={"cnpj_basico": pl.Utf8})

    assert bulk_copy_active_filtered(conn, df, "empresas", ["cnpj_basico"]) == 0


def test_active_filtered_copy_requires_cnpj_basico():
    conn, _ = _mock_conn()
    df = pl.DataFrame({"id": ["1"]})

    with pytest.raises(ValueError, match="cnpj_basico"):
        bulk_copy_active_filtered(conn, df, "empresas", ["id"])


def test_active_filtered_copy_uses_staging_join():
    conn, cur = _mock_conn()
    cur.rowcount = 1
    df = pl.DataFrame({"cnpj_basico": ["00000001"], "razao_social": ["A"]})

    with patch("loader.bulk_copy", return_value=1) as mock_copy:
        result = bulk_copy_active_filtered(
            conn,
            df,
            "empresas",
            ["cnpj_basico", "razao_social"],
            commit=True,
        )

    assert result == 1
    assert conn.commit.called
    mock_copy.assert_called_once()
    calls = [c[0][0] for c in cur.execute.call_args_list]
    assert any("JOIN etl_active_cnpjs" in sql for sql in calls)
    assert any(sql.startswith("DROP TABLE _etl_stage_empresas_") for sql in calls)


def test_active_filtered_copy_adds_upsert_clause():
    conn, cur = _mock_conn()
    cur.rowcount = 1
    df = pl.DataFrame({"cnpj_basico": ["00000001"], "razao_social": ["A"]})

    with patch("loader.bulk_copy", return_value=1):
        bulk_copy_active_filtered(
            conn,
            df,
            "empresas",
            ["cnpj_basico", "razao_social"],
            conflict_columns=["cnpj_basico"],
        )

    calls = [c[0][0] for c in cur.execute.call_args_list]
    assert any(
        "ON CONFLICT (cnpj_basico) DO UPDATE SET "
        "razao_social = EXCLUDED.razao_social" in sql
        for sql in calls
    )


def test_active_filtered_copy_uses_do_nothing_when_all_columns_conflict():
    conn, cur = _mock_conn()
    cur.rowcount = 1
    df = pl.DataFrame({"cnpj_basico": ["00000001"]})

    with patch("loader.bulk_copy", return_value=1):
        bulk_copy_active_filtered(
            conn,
            df,
            "empresas",
            ["cnpj_basico"],
            conflict_columns=["cnpj_basico"],
        )

    calls = [c[0][0] for c in cur.execute.call_args_list]
    assert any("ON CONFLICT (cnpj_basico) DO NOTHING" in sql for sql in calls)
