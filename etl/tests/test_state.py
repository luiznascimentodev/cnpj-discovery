"""Testes para etl/state.py — requerem PostgreSQL."""
from datetime import datetime, timezone, timedelta

import psycopg2
import pytest

from config import Settings
from state import (
    ETLFileState,
    get_file_state,
    set_file_state,
    needs_update,
    get_all_states,
)


@pytest.fixture(scope="module")
def conn():
    s = Settings(postgres_password="changeme")
    c = psycopg2.connect(s.dsn)
    yield c
    c.close()


@pytest.fixture(autouse=True)
def clean_state(conn):
    with conn.cursor() as cur:
        cur.execute("DELETE FROM etl_state WHERE arquivo LIKE '_test_%'")
    conn.commit()


NOW = datetime(2024, 6, 1, 12, 0, 0, tzinfo=timezone.utc)
OLDER = datetime(2024, 5, 1, 12, 0, 0, tzinfo=timezone.utc)
NEWER = datetime(2024, 7, 1, 12, 0, 0, tzinfo=timezone.utc)


class TestETLFileState:
    def test_constructor(self):
        s = ETLFileState("test.zip", "done")
        assert s.arquivo == "test.zip"
        assert s.status == "done"
        assert s.rows_processed == 0
        assert s.error_message is None


class TestGetFileState:
    def test_returns_none_for_unknown_file(self, conn):
        result = get_file_state(conn, "_test_unknown.zip")
        assert result is None

    def test_returns_state_after_set(self, conn):
        set_file_state(conn, "_test_file.zip", "done", NOW, rows_processed=100)
        result = get_file_state(conn, "_test_file.zip")
        assert result is not None
        assert result.status == "done"
        assert result.rows_processed == 100


class TestSetFileState:
    def test_inserts_new_state(self, conn):
        set_file_state(conn, "_test_new.zip", "pending")
        result = get_file_state(conn, "_test_new.zip")
        assert result.status == "pending"

    def test_updates_existing_state(self, conn):
        set_file_state(conn, "_test_update.zip", "downloading", NOW)
        set_file_state(conn, "_test_update.zip", "done", NOW, rows_processed=500)
        result = get_file_state(conn, "_test_update.zip")
        assert result.status == "done"
        assert result.rows_processed == 500

    def test_stores_error_message(self, conn):
        set_file_state(conn, "_test_err.zip", "error", error_message="Connection timeout")
        result = get_file_state(conn, "_test_err.zip")
        assert result.error_message == "Connection timeout"


class TestNeedsUpdate:
    def test_true_for_unknown_file(self, conn):
        assert needs_update(conn, "_test_new.zip", NOW) is True

    def test_true_for_error_status(self, conn):
        set_file_state(conn, "_test_err.zip", "error", NOW)
        assert needs_update(conn, "_test_err.zip", NOW) is True

    def test_true_for_newer_remote(self, conn):
        set_file_state(conn, "_test_old.zip", "done", OLDER)
        assert needs_update(conn, "_test_old.zip", NOW) is True

    def test_false_for_same_date_done(self, conn):
        set_file_state(conn, "_test_same.zip", "done", NOW)
        assert needs_update(conn, "_test_same.zip", NOW) is False

    def test_false_for_older_remote(self, conn):
        set_file_state(conn, "_test_newer.zip", "done", NOW)
        assert needs_update(conn, "_test_newer.zip", OLDER) is False

    def test_true_for_null_last_modified(self, conn):
        set_file_state(conn, "_test_null.zip", "done", last_modified=None)
        assert needs_update(conn, "_test_null.zip", NOW) is True

    def test_true_for_pending_status(self, conn):
        set_file_state(conn, "_test_pend.zip", "pending", NOW)
        assert needs_update(conn, "_test_pend.zip", NOW) is True

    def test_handles_naive_datetime(self, conn):
        naive_now = datetime(2024, 6, 1, 12, 0, 0)  # sem tzinfo
        set_file_state(conn, "_test_naive.zip", "done", NOW)
        result = needs_update(conn, "_test_naive.zip", naive_now)
        assert isinstance(result, bool)

    def test_handles_naive_local_datetime(self, conn):
        # Testa o branch local.tzinfo is None usando mock do get_file_state
        from unittest.mock import patch
        naive_last_modified = datetime(2024, 5, 1, 12, 0, 0)  # sem tzinfo
        mock_state = ETLFileState(
            arquivo="_test_naive_local.zip",
            status="done",
            last_modified=naive_last_modified,
        )
        with patch("state.get_file_state", return_value=mock_state):
            # NEWER is after naive_last_modified — should return True
            result = needs_update(conn, "_test_naive_local.zip", NEWER)
        assert result is True


class TestGetAllStates:
    def test_returns_list(self, conn):
        result = get_all_states(conn)
        assert isinstance(result, list)

    def test_returns_etl_file_state_objects(self, conn):
        set_file_state(conn, "_test_list.zip", "done", NOW)
        result = get_all_states(conn)
        for item in result:
            assert isinstance(item, ETLFileState)

    def test_contains_inserted_state(self, conn):
        set_file_state(conn, "_test_all.zip", "done", NOW, rows_processed=42)
        result = get_all_states(conn)
        files = [s.arquivo for s in result]
        assert "_test_all.zip" in files
