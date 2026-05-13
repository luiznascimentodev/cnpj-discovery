"""
CNPJ Discovery ETL — CLI orquestrador.

Comandos:
    python main.py full-load   Carga inicial completa (download + ETL + índices)
    python main.py update      Atualização incremental (apenas arquivos novos/modificados)
    python main.py status      Exibe o estado atual de todos os arquivos processados
"""
import argparse
import shutil
import sys
from pathlib import Path
from queue import Queue
from threading import Thread

from loguru import logger

from config import settings
from downloader import list_rf_files, download_file, RFFile
from extractor import stream_zip_as_batches
from transformer import TRANSFORM_MAP
from loader import (
    get_connection,
    bulk_copy,
    bulk_copy_active_filtered,
    upsert,
    disable_triggers,
    enable_triggers,
    rebuild_active_cnpj_filter,
    drop_active_cnpj_filter,
)
import psycopg2
import polars as pl

from indexer import drop_managed_indexes, create_managed_indexes, MANAGED_INDEXES
from state import get_file_state, set_file_state, needs_update, get_all_states
from schemas import MAIN_FILE_SCHEMAS, FILE_PREFIX_MAP
from dataset_sources import choose_load_snapshot, discover_dataset_snapshots
from dataset_state import (
    get_pending_snapshot,
    mark_snapshot_failed,
    mark_snapshot_loaded,
    record_snapshot,
    release_refresh_lock,
    try_refresh_lock,
)


def _get_schema_for_file(filename: str):
    """Retorna o TableSchema adequado para um arquivo RF, ou None se não conhecido."""
    normalized_filename = filename.lower()
    for prefix, schema in {**MAIN_FILE_SCHEMAS, **FILE_PREFIX_MAP}.items():
        if normalized_filename.startswith(prefix.lower()):
            return schema
    return None


_ACTIVE_FILTERED_TABLES = {"empresas", "simples", "socios"}


def _active_only_batch_filter(df, table: str):
    if table != "estabelecimentos":
        return df
    before = len(df)
    filtered = df.filter(pl.col("situacao_cadastral") == 2)
    removed = before - len(filtered)
    if removed:
        logger.debug(f"Active-only filter removed {removed:,}/{before:,} estabelecimentos rows")
    return filtered


def _process_file(
    conn,
    rf_file: RFFile,
    mode: str = "copy",
    zip_path: Path = None,
    active_only: bool = False,
    filter_by_active_cnpj: bool = False,
) -> int:
    """
    Processa um único arquivo ZIP: (download →) extract → transform → load.

    zip_path: se fornecido, o download já foi feito pelo pipeline e é pulado aqui.
    mode: 'copy' para carga inicial (bulk COPY), 'upsert' para atualização incremental.
    """
    schema = _get_schema_for_file(rf_file.name)
    if schema is None:
        logger.warning(f"Unknown file type: {rf_file.name} — skipping")
        return 0

    if zip_path is None:
        # Modo standalone (cmd_update): download acontece aqui
        set_file_state(conn, rf_file.name, "downloading", rf_file.last_modified)
        try:
            zip_path = download_file(rf_file, settings.etl_data_dir)
        except Exception as e:
            set_file_state(conn, rf_file.name, "error", rf_file.last_modified, error_message=str(e))
            raise

    set_file_state(conn, rf_file.name, "loading", rf_file.last_modified)

    transform_fn = TRANSFORM_MAP.get(schema.table)
    total_rows = 0

    try:
        if mode == "copy":
            disable_triggers(conn, schema.table)

        for batch_df in stream_zip_as_batches(zip_path, schema.columns, settings.etl_batch_size):
            if transform_fn:
                batch_df = transform_fn(batch_df)
            if active_only:
                batch_df = _active_only_batch_filter(batch_df, schema.table)
            if len(batch_df) == 0:
                continue
            if mode == "copy":
                if filter_by_active_cnpj and schema.table in _ACTIVE_FILTERED_TABLES:
                    total_rows += bulk_copy_active_filtered(
                        conn, batch_df, schema.table, schema.columns
                    )
                else:
                    total_rows += bulk_copy(conn, batch_df, schema.table, schema.columns)
            else:
                if filter_by_active_cnpj and schema.table in _ACTIVE_FILTERED_TABLES:
                    total_rows += bulk_copy_active_filtered(
                        conn,
                        batch_df,
                        schema.table,
                        schema.columns,
                        conflict_columns=schema.conflict_columns,
                        commit=True,
                    )
                else:
                    total_rows += upsert(
                        conn, batch_df, schema.table, schema.columns, schema.conflict_columns
                    )

        if mode == "copy":
            enable_triggers(conn, schema.table)
            conn.commit()
    except Exception as e:
        conn.rollback()
        logger.exception(f"Failed while processing {rf_file.name}")
        if mode == "copy":
            try:
                enable_triggers(conn, schema.table)
            except Exception:
                conn.rollback()
                logger.exception(f"Failed to re-enable triggers on {schema.table}")
        set_file_state(conn, rf_file.name, "error", rf_file.last_modified, error_message=str(e))
        raise
    finally:
        if zip_path and zip_path.exists() and not settings.etl_keep_zips_after_load:
            zip_path.unlink()
            logger.debug(f"Deleted {zip_path}")

    set_file_state(conn, rf_file.name, "done", rf_file.last_modified, rows_processed=total_rows)
    logger.success(f"{rf_file.name}: {total_rows:,} rows loaded into {schema.table}")
    return total_rows


def _run_file_pipeline(
    files: list[RFFile],
    *,
    active_only: bool,
    filter_by_active_cnpj: bool,
    raise_on_error: bool = False,
) -> None:
    if not files:
        return

    n_dl = settings.etl_download_workers
    n_proc = settings.etl_process_workers
    logger.info(f"Pipeline: {n_dl} download workers → {n_proc} process workers ({len(files)} files)")

    # Queue com backpressure: no máximo n_proc * 2 ZIPs aguardando processamento em disco
    process_queue: Queue = Queue(maxsize=n_proc * 2)
    errors: list[str] = []

    def _download_worker(file_list: list):
        for rf_file in file_list:
            if _get_schema_for_file(rf_file.name) is None:
                logger.warning(f"Unknown file type: {rf_file.name} — skipping")
                continue
            with get_connection() as conn:
                set_file_state(conn, rf_file.name, "downloading", rf_file.last_modified)
            try:
                zip_path = download_file(rf_file, settings.etl_data_dir)
                process_queue.put((rf_file, zip_path))  # bloqueia se a fila estiver cheia
            except Exception as e:
                logger.error(f"Download failed: {rf_file.name}: {e}")
                errors.append(f"{rf_file.name}: {e}")
                with get_connection() as conn:
                    set_file_state(conn, rf_file.name, "error", rf_file.last_modified, error_message=str(e))

    def _process_worker():
        while True:
            item = process_queue.get()
            if item is None:
                process_queue.task_done()
                break
            rf_file, zip_path = item
            try:
                with get_connection(fast_write=True) as conn:
                    _process_file(
                        conn,
                        rf_file,
                        mode="copy",
                        zip_path=zip_path,
                        active_only=active_only,
                        filter_by_active_cnpj=filter_by_active_cnpj,
                    )
            except Exception as e:
                logger.error(f"Process failed: {rf_file.name}: {e}")
                errors.append(f"{rf_file.name}: {e}")
            finally:
                process_queue.task_done()

    file_chunks = [files[i::n_dl] for i in range(n_dl)]
    dl_threads = [Thread(target=_download_worker, args=(chunk,), daemon=True) for chunk in file_chunks]
    proc_threads = [Thread(target=_process_worker, daemon=True) for _ in range(n_proc)]

    for t in proc_threads:
        t.start()
    for t in dl_threads:
        t.start()
    for t in dl_threads:
        t.join()
    for _ in range(n_proc):
        process_queue.put(None)
    for t in proc_threads:
        t.join()

    if raise_on_error and errors:
        raise RuntimeError(f"ETL pipeline failed for {len(errors)} file(s): {'; '.join(errors[:5])}")


def _partition_active_only_load(files: list[RFFile]) -> tuple[list[RFFile], list[RFFile], list[RFFile]]:
    bootstrap: list[RFFile] = []
    establishments: list[RFFile] = []
    active_dependents: list[RFFile] = []

    for rf_file in files:
        schema = _get_schema_for_file(rf_file.name)
        if schema is None:
            bootstrap.append(rf_file)
        elif schema.table == "estabelecimentos":
            establishments.append(rf_file)
        elif schema.table in _ACTIVE_FILTERED_TABLES:
            active_dependents.append(rf_file)
        else:
            bootstrap.append(rf_file)

    return bootstrap, establishments, active_dependents


def cmd_full_load():
    """
    Carga inicial completa com pipeline separado:
      - etl_download_workers (2) fazem download em paralelo, limitando pressão no WebDAV da RF
      - etl_process_workers (6) processam (extract + transform + load) em paralelo
      - Queue com backpressure evita acúmulo excessivo de ZIPs em disco
    """
    logger.info("Starting FULL LOAD...")
    rf_files = list_rf_files()
    logger.info(f"Found {len(rf_files)} files to process")

    # Fase 1: setup
    with get_connection() as conn:
        drop_managed_indexes(conn)
        to_process = []
        for rf_file in rf_files:
            state = get_file_state(conn, rf_file.name)
            if state and state.status == "done":
                logger.info(f"Skipping {rf_file.name} — already done ({state.rows_processed:,} rows)")
            else:
                to_process.append(rf_file)

    if not to_process:
        logger.info("Nothing to process.")
    else:
        if settings.etl_active_only:
            logger.info("Active-only ETL enabled: loading only open/active CNPJs")
            bootstrap, establishments, active_dependents = _partition_active_only_load(to_process)
            _run_file_pipeline(
                bootstrap + establishments,
                active_only=True,
                filter_by_active_cnpj=False,
                raise_on_error=True,
            )
            if active_dependents:
                if not establishments:
                    raise RuntimeError("ETL_ACTIVE_ONLY requires Estabelecimentos files to build active filter")
                with get_connection() as conn:
                    rebuild_active_cnpj_filter(conn)
                try:
                    _run_file_pipeline(
                        active_dependents,
                        active_only=True,
                        filter_by_active_cnpj=True,
                        raise_on_error=True,
                    )
                finally:
                    with get_connection() as conn:
                        drop_active_cnpj_filter(conn)
        else:
            _run_file_pipeline(to_process, active_only=False, filter_by_active_cnpj=False)

    # Fase 3: recriar índices
    with get_connection() as conn:
        create_managed_indexes(conn)

    # Fase 4: atualizar estatísticas para o planner do PostgreSQL
    _vacuum_analyze_all()

    logger.success("Full load completed!")


def _vacuum_analyze_all():
    """Executa VACUUM ANALYZE em todas as tabelas gerenciadas.

    VACUUM não pode rodar dentro de transação, por isso usa conexão própria
    com autocommit=True, sem passar por get_connection().
    """
    # Extrai nomes de tabela únicos do MANAGED_INDEXES ("ON tabela ...")
    tables = sorted({_table_from_sql(sql) for _, sql in MANAGED_INDEXES})
    logger.info(f"Running VACUUM ANALYZE on {len(tables)} tables: {', '.join(tables)}")
    conn = psycopg2.connect(settings.dsn)
    conn.autocommit = True
    try:
        with conn.cursor() as cur:
            for table in tables:
                logger.info(f"VACUUM ANALYZE {table}...")
                cur.execute(f"VACUUM ANALYZE {table}")
                logger.success(f"VACUUM ANALYZE {table} done")
    finally:
        conn.close()
    logger.success("VACUUM ANALYZE completed")


def _table_from_sql(sql: str) -> str:
    """Extrai o nome da tabela de uma instrução CREATE INDEX ... ON tabela ...."""
    # Tudo após 'ON ' até o próximo espaço ou nova linha
    after_on = sql.split("ON ", 1)[1]
    return after_on.split()[0]


def cmd_update():
    """Atualização incremental: apenas arquivos novos ou modificados."""
    if settings.etl_active_only:
        raise RuntimeError(
            "Incremental update is disabled when ETL_ACTIVE_ONLY=true. "
            "Run a fresh full-load so inactive CNPJs are removed consistently."
        )

    logger.info("Starting INCREMENTAL UPDATE...")
    rf_files = list_rf_files()

    with get_connection() as conn:
        files_to_update = [
            f for f in rf_files
            if needs_update(conn, f.name, f.last_modified)
        ]

        if not files_to_update:
            logger.info("No files need updating. Everything is up to date.")
            return

        logger.info(f"{len(files_to_update)} files need updating")

        for rf_file in files_to_update:
            try:
                _process_file(conn, rf_file, mode="upsert")
            except Exception as e:
                logger.error(f"Failed to update {rf_file.name}: {e}")
                continue

    logger.success("Update completed!")


def cmd_status():
    """Exibe o estado atual de todos os arquivos processados."""
    with get_connection() as conn:
        states = get_all_states(conn)

    if not states:
        print("No ETL state recorded yet. Run 'full-load' first.")
        return

    print(f"\n{'Arquivo':<40} {'Status':<12} {'Rows':>12} {'Loaded At'}")
    print("-" * 80)
    for s in states:
        loaded = s.loaded_at.strftime("%Y-%m-%d %H:%M") if s.loaded_at else "N/A"
        print(f"{s.arquivo:<40} {s.status:<12} {s.rows_processed:>12,} {loaded}")
    print()


def cmd_check_public_data():
    """Descobre snapshots publicos da Receita em multiplas fontes e registra manifesto."""
    logger.info("Checking public CNPJ dataset sources...")
    snapshots = discover_dataset_snapshots()
    selected = choose_load_snapshot(snapshots)

    if not snapshots:
        raise RuntimeError("No public CNPJ dataset source returned files")

    with get_connection() as conn:
        for snapshot in snapshots:
            snapshot_id, status = record_snapshot(
                conn,
                snapshot,
                selected=bool(selected and snapshot.source_name == selected.source_name
                              and snapshot.snapshot_key == selected.snapshot_key),
            )
            logger.info(
                "dataset_snapshot id={} source={} key={} files={} bytes={} status={}",
                snapshot_id,
                snapshot.source_name,
                snapshot.snapshot_key,
                snapshot.file_count,
                snapshot.total_size_bytes,
                status,
            )

    if selected:
        logger.success(
            "Selected public dataset snapshot source={} key={} files={}",
            selected.source_name,
            selected.snapshot_key,
            selected.file_count,
        )
    else:
        logger.warning("No loadable bulk snapshot found; metadata sources were recorded only")


def _ensure_enough_free_space():
    Path(settings.etl_data_dir).mkdir(parents=True, exist_ok=True)
    usage = shutil.disk_usage(settings.etl_data_dir)
    free_gb = usage.free / (1024 ** 3)
    if free_gb < settings.etl_min_free_gb:
        raise RuntimeError(
            f"Insufficient free disk space: {free_gb:.1f} GB available, "
            f"{settings.etl_min_free_gb} GB required"
        )
    logger.info("Free disk space OK: {:.1f} GB", free_gb)


def _validate_active_only_result():
    if not settings.etl_active_only:
        return
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT count(*) FROM estabelecimentos "
                "WHERE situacao_cadastral IS DISTINCT FROM 2"
            )
            inactive_count = cur.fetchone()[0]
    if inactive_count:
        raise RuntimeError(f"Active-only validation failed: {inactive_count} inactive rows found")


def cmd_refresh_active_only_if_updated():
    """Executa refresh ativa-only somente quando ha snapshot pendente e flag habilitada."""
    with get_connection() as lock_conn:
        if not try_refresh_lock(lock_conn):
            logger.warning("Another ETL refresh is already running")
            return
        try:
            pending = get_pending_snapshot(lock_conn)
            if not pending:
                logger.info("No pending public dataset snapshot to load")
                return

            snapshot_id = pending[0]
            if not settings.etl_auto_load_public_data:
                logger.info(
                    "Snapshot {} is pending, but ETL_AUTO_LOAD_PUBLIC_DATA=false; "
                    "leaving it queued for manual approval",
                    snapshot_id,
                )
                return

            try:
                _ensure_enough_free_space()
                cmd_full_load()
                _validate_active_only_result()
                with get_connection() as conn:
                    mark_snapshot_loaded(conn, snapshot_id)
            except Exception as exc:
                with get_connection() as conn:
                    mark_snapshot_failed(conn, snapshot_id, str(exc))
                raise
        finally:
            release_refresh_lock(lock_conn)


def main():
    parser = argparse.ArgumentParser(
        description="CNPJ Discovery ETL — Receita Federal data pipeline"
    )
    subparsers = parser.add_subparsers(dest="command", required=True)
    subparsers.add_parser("full-load", help="Initial full load of all RF files")
    subparsers.add_parser("update", help="Incremental update of new/modified files")
    subparsers.add_parser("status", help="Show current ETL state for all files")
    subparsers.add_parser("check-public-data", help="Check public CNPJ dataset snapshots")
    subparsers.add_parser(
        "refresh-active-only-if-updated",
        help="Run active-only full-load when a validated public snapshot is pending",
    )

    args = parser.parse_args()

    if args.command == "full-load":
        cmd_full_load()
    elif args.command == "update":
        cmd_update()
    elif args.command == "status":
        cmd_status()
    elif args.command == "check-public-data":
        cmd_check_public_data()
    elif args.command == "refresh-active-only-if-updated":
        cmd_refresh_active_only_if_updated()


if __name__ == "__main__":
    main()
