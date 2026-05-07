"""
Loader ETL — inserção em massa de dados no PostgreSQL.

Duas estratégias:
1. COPY FROM STDIN (bulk load inicial): 10-50x mais rápido que INSERT
2. execute_values com ON CONFLICT DO UPDATE (atualização incremental)
"""
import io
from contextlib import contextmanager
from typing import Generator

import polars as pl
import psycopg2
import psycopg2.extras
from loguru import logger

from config import settings


@contextmanager
def get_connection(fast_write: bool = False) -> Generator[psycopg2.extensions.connection, None, None]:
    """
    Context manager para conexão PostgreSQL com auto-commit controlado.

    fast_write=True: desativa synchronous_commit nesta sessão. Reduz latência
    por chamada de COPY em cargas massivas. O risco é perder até ~1 s de dados
    numa queda; para um ETL re-executável isso é aceitável.
    """
    conn = psycopg2.connect(settings.dsn)
    try:
        if fast_write:
            with conn.cursor() as cur:
                cur.execute("SET synchronous_commit = off")
        yield conn
    finally:
        conn.close()


def disable_triggers(conn: psycopg2.extensions.connection, table: str) -> None:
    """
    Desativa triggers na tabela durante carga inicial.
    Triggers validam FK e outros constraints — desativar acelera o COPY massivamente.
    Requer superuser ou ownership da tabela.
    Não faz commit — deve ser chamado dentro da mesma transação da carga.
    """
    with conn.cursor() as cur:
        cur.execute(f"ALTER TABLE {table} DISABLE TRIGGER ALL")
    logger.debug(f"Triggers disabled on {table}")


def enable_triggers(conn: psycopg2.extensions.connection, table: str) -> None:
    """
    Reativa triggers após a carga.
    Não faz commit — o commit deve ser feito pelo chamador após todos os batches.
    """
    with conn.cursor() as cur:
        cur.execute(f"ALTER TABLE {table} ENABLE TRIGGER ALL")
    logger.debug(f"Triggers enabled on {table}")


def bulk_copy(
    conn: psycopg2.extensions.connection,
    df: pl.DataFrame,
    table: str,
    columns: list[str],
    commit: bool = False,
) -> int:
    """
    Insere um DataFrame no PostgreSQL via COPY FROM STDIN (FORMAT CSV).

    Por padrão não commita — o chamador é responsável pelo commit após todos
    os batches, tornando o carregamento de um arquivo inteiro atômico.

    Returns:
        Número de linhas inseridas
    """
    available_cols = [c for c in columns if c in df.columns]
    df_subset = df.select(available_cols)

    buf = io.BytesIO()
    df_subset.write_csv(
        buf,
        separator="\t",
        null_value="\\N",
        include_header=False,
    )
    buf.seek(0)

    columns_sql = ", ".join(available_cols)
    copy_sql = (
        f"COPY {table} ({columns_sql}) FROM STDIN WITH "
        "(FORMAT CSV, DELIMITER E'\\t', NULL '\\N', HEADER FALSE)"
    )

    with conn.cursor() as cur:
        cur.copy_expert(copy_sql, buf)

    if commit:
        conn.commit()

    n_rows = len(df)
    logger.debug(f"COPY {n_rows} rows → {table}")
    return n_rows


def upsert(
    conn: psycopg2.extensions.connection,
    df: pl.DataFrame,
    table: str,
    columns: list[str],
    conflict_columns: list[str],
) -> int:
    """
    Insere/atualiza registros via INSERT ... ON CONFLICT DO UPDATE.

    Usado para atualizações mensais incrementais onde queremos:
    - Inserir empresas novas
    - Atualizar dados de empresas existentes

    Args:
        conflict_columns: Colunas que formam a chave de conflito (PK ou unique)

    Returns:
        Número de linhas processadas (inseridas + atualizadas)
    """
    if not conflict_columns:
        # Tabelas como socios são append-only — não fazem upsert
        return bulk_copy(conn, df, table, columns)

    available_cols = [c for c in columns if c in df.columns]
    update_cols = [c for c in available_cols if c not in conflict_columns]

    if not update_cols:
        # Todas as colunas são PK — só INSERT OR IGNORE
        sql = (
            f"INSERT INTO {table} ({', '.join(available_cols)}) VALUES %s "
            f"ON CONFLICT ({', '.join(conflict_columns)}) DO NOTHING"
        )
    else:
        update_clause = ", ".join(f"{c} = EXCLUDED.{c}" for c in update_cols)
        sql = (
            f"INSERT INTO {table} ({', '.join(available_cols)}) VALUES %s "
            f"ON CONFLICT ({', '.join(conflict_columns)}) DO UPDATE SET {update_clause}"
        )

    rows = df.select(available_cols).rows()

    with conn.cursor() as cur:
        psycopg2.extras.execute_values(cur, sql, rows, page_size=5_000)
    conn.commit()

    n_rows = len(rows)
    logger.debug(f"UPSERT {n_rows} rows → {table}")
    return n_rows
