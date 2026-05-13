from dataset_sources import DatasetSnapshot

_SQL_UPSERT_SNAPSHOT = """
    INSERT INTO app_private.etl_dataset_snapshots (
        snapshot_key, source_name, source_url, status, selected_at,
        manifest_hash, file_count, total_size_bytes, last_modified_max
    )
    VALUES (%s, %s, %s, %s, now(), %s, %s, %s, %s)
    ON CONFLICT (source_name, snapshot_key) DO UPDATE SET
        source_url = EXCLUDED.source_url,
        manifest_hash = EXCLUDED.manifest_hash,
        file_count = EXCLUDED.file_count,
        total_size_bytes = EXCLUDED.total_size_bytes,
        last_modified_max = EXCLUDED.last_modified_max
    RETURNING id, status
"""

_SQL_UPSERT_FILE = """
    INSERT INTO app_private.etl_dataset_files (
        snapshot_id, file_name, url, size_bytes, etag, last_modified, sha256
    )
    VALUES (%s, %s, %s, %s, %s, %s, %s)
    ON CONFLICT (snapshot_id, file_name) DO UPDATE SET
        url = EXCLUDED.url,
        size_bytes = EXCLUDED.size_bytes,
        etag = EXCLUDED.etag,
        last_modified = EXCLUDED.last_modified,
        sha256 = EXCLUDED.sha256
"""

_SQL_PENDING_SNAPSHOT = """
    SELECT id, snapshot_key, source_name
    FROM app_private.etl_dataset_snapshots
    WHERE status = 'pending_load'
    ORDER BY discovered_at DESC, id DESC
    LIMIT 1
"""

_SQL_MARK_LOADED = """
    UPDATE app_private.etl_dataset_snapshots
    SET status = 'loaded', loaded_at = now(), last_error = NULL
    WHERE id = %s
"""

_SQL_MARK_FAILED = """
    UPDATE app_private.etl_dataset_snapshots
    SET status = 'failed', last_error = %s
    WHERE id = %s
"""

_SQL_TRY_LOCK = "SELECT pg_try_advisory_lock(%s)"
_SQL_UNLOCK = "SELECT pg_advisory_unlock(%s)"

ETL_REFRESH_LOCK_ID = 81420260513


def record_snapshot(conn, snapshot: DatasetSnapshot, *, selected: bool) -> tuple[int, str]:
    status = "pending_load" if selected else "discovered"
    with conn.cursor() as cur:
        cur.execute(
            _SQL_UPSERT_SNAPSHOT,
            (
                snapshot.snapshot_key,
                snapshot.source_name,
                snapshot.source_url,
                status,
                snapshot.manifest_hash,
                snapshot.file_count,
                snapshot.total_size_bytes,
                snapshot.last_modified_max,
            ),
        )
        snapshot_id, current_status = cur.fetchone()
        for file in snapshot.files:
            cur.execute(
                _SQL_UPSERT_FILE,
                (
                    snapshot_id,
                    file.file_name,
                    file.url,
                    file.size_bytes,
                    file.etag,
                    file.last_modified,
                    file.sha256,
                ),
            )
    conn.commit()
    return snapshot_id, current_status


def get_pending_snapshot(conn):
    with conn.cursor() as cur:
        cur.execute(_SQL_PENDING_SNAPSHOT)
        return cur.fetchone()


def mark_snapshot_loaded(conn, snapshot_id: int) -> None:
    with conn.cursor() as cur:
        cur.execute(_SQL_MARK_LOADED, (snapshot_id,))
    conn.commit()


def mark_snapshot_failed(conn, snapshot_id: int, error: str) -> None:
    with conn.cursor() as cur:
        cur.execute(_SQL_MARK_FAILED, (error, snapshot_id))
    conn.commit()


def try_refresh_lock(conn) -> bool:
    with conn.cursor() as cur:
        cur.execute(_SQL_TRY_LOCK, (ETL_REFRESH_LOCK_ID,))
        return bool(cur.fetchone()[0])


def release_refresh_lock(conn) -> None:
    with conn.cursor() as cur:
        cur.execute(_SQL_UNLOCK, (ETL_REFRESH_LOCK_ID,))
    conn.commit()
