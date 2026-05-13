from datetime import datetime, timezone

from dataset_sources import DatasetFile, DatasetSnapshot
from dataset_state import (
    ETL_REFRESH_LOCK_ID,
    get_pending_snapshot,
    mark_snapshot_failed,
    mark_snapshot_loaded,
    record_snapshot,
    release_refresh_lock,
    try_refresh_lock,
)


class FakeCursor:
    def __init__(self):
        self.queries = []
        self.fetchone_value = (10, "pending_load")

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, traceback):
        return False

    def execute(self, query, args=None):
        self.queries.append((query, args))

    def fetchone(self):
        return self.fetchone_value


class FakeConn:
    def __init__(self):
        self.cur = FakeCursor()
        self.commits = 0

    def cursor(self):
        return self.cur

    def commit(self):
        self.commits += 1


def _snapshot():
    return DatasetSnapshot(
        source_name="rf_http_index",
        snapshot_key="2024-03",
        source_url="https://example.test/",
        files=[
            DatasetFile(
                "Empresas0.zip",
                "https://example.test/Empresas0.zip",
                123,
                datetime(2024, 3, 1, tzinfo=timezone.utc),
                "etag",
                "sha",
            )
        ],
    )


class TestDatasetState:
    def test_record_snapshot_upserts_snapshot_and_files(self):
        conn = FakeConn()
        snapshot_id, status = record_snapshot(conn, _snapshot(), selected=True)

        assert snapshot_id == 10
        assert status == "pending_load"
        assert len(conn.cur.queries) == 2
        assert conn.commits == 1

    def test_get_pending_snapshot_fetches_one(self):
        conn = FakeConn()
        assert get_pending_snapshot(conn) == (10, "pending_load")

    def test_mark_loaded_and_failed_commit(self):
        conn = FakeConn()
        mark_snapshot_loaded(conn, 10)
        mark_snapshot_failed(conn, 10, "boom")

        assert conn.commits == 2

    def test_lock_helpers_use_constant(self):
        conn = FakeConn()
        conn.cur.fetchone_value = (True,)

        assert try_refresh_lock(conn) is True
        release_refresh_lock(conn)

        lock_args = conn.cur.queries[0][1]
        assert lock_args == (ETL_REFRESH_LOCK_ID,)
