"""
CNPJ Discovery ETL — CLI orquestrador.

Comandos:
    python main.py full-load   Carga inicial completa (download + ETL + índices)
    python main.py update      Atualização incremental (apenas arquivos novos/modificados)
    python main.py status      Exibe o estado atual de todos os arquivos processados
"""
import argparse
import sys
from datetime import timezone
from pathlib import Path

from loguru import logger

from config import settings
from downloader import list_rf_files, download_file, RFFile
from extractor import stream_zip_as_batches
from transformer import TRANSFORM_MAP
from loader import get_connection, bulk_copy, upsert, disable_triggers, enable_triggers
from indexer import drop_managed_indexes, create_managed_indexes
from state import get_file_state, set_file_state, needs_update, get_all_states
from schemas import MAIN_FILE_SCHEMAS, FILE_PREFIX_MAP


def _get_schema_for_file(filename: str):
    """Retorna o TableSchema adequado para um arquivo RF, ou None se não conhecido."""
    normalized_filename = filename.lower()
    for prefix, schema in {**MAIN_FILE_SCHEMAS, **FILE_PREFIX_MAP}.items():
        if normalized_filename.startswith(prefix.lower()):
            return schema
    return None


def _process_file(conn, rf_file: RFFile, mode: str = "copy") -> int:
    """
    Processa um único arquivo ZIP: download → extract → transform → load.

    Args:
        mode: 'copy' para carga inicial (bulk COPY), 'upsert' para atualização incremental

    Returns:
        Total de linhas processadas
    """
    schema = _get_schema_for_file(rf_file.name)
    if schema is None:
        logger.warning(f"Unknown file type: {rf_file.name} — skipping")
        return 0

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
            if mode == "copy":
                total_rows += bulk_copy(conn, batch_df, schema.table, schema.columns)
            else:
                total_rows += upsert(
                    conn, batch_df, schema.table, schema.columns, schema.conflict_columns
                )

        if mode == "copy":
            enable_triggers(conn, schema.table)
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
        # Apagar ZIP independente de sucesso/falha para liberar disco
        if zip_path.exists():
            zip_path.unlink()
            logger.debug(f"Deleted {zip_path}")

    set_file_state(conn, rf_file.name, "done", rf_file.last_modified, rows_processed=total_rows)
    logger.success(f"{rf_file.name}: {total_rows} rows loaded into {schema.table}")
    return total_rows


def cmd_full_load():
    """Carga inicial completa: drop índices → processar todos → recriar índices."""
    logger.info("Starting FULL LOAD...")
    rf_files = list_rf_files()
    logger.info(f"Found {len(rf_files)} files to process")

    with get_connection() as conn:
        drop_managed_indexes(conn)

        for rf_file in rf_files:
            state = get_file_state(conn, rf_file.name)
            if state and state.status == "done":
                logger.info(f"Skipping {rf_file.name} — already done ({state.rows_processed:,} rows)")
                continue
            try:
                _process_file(conn, rf_file, mode="copy")
            except Exception as e:
                conn.rollback()
                logger.error(f"Failed to process {rf_file.name}: {e}")
                # Continua para o próximo arquivo
                continue

        create_managed_indexes(conn)

    logger.success("Full load completed!")


def cmd_update():
    """Atualização incremental: apenas arquivos novos ou modificados."""
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


def main():
    parser = argparse.ArgumentParser(
        description="CNPJ Discovery ETL — Receita Federal data pipeline"
    )
    subparsers = parser.add_subparsers(dest="command", required=True)
    subparsers.add_parser("full-load", help="Initial full load of all RF files")
    subparsers.add_parser("update", help="Incremental update of new/modified files")
    subparsers.add_parser("status", help="Show current ETL state for all files")

    args = parser.parse_args()

    if args.command == "full-load":
        cmd_full_load()
    elif args.command == "update":
        cmd_update()
    elif args.command == "status":
        cmd_status()


if __name__ == "__main__":
    main()
