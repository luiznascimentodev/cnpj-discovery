"""
Loader ETL — inserção em massa de dados no PostgreSQL.

Duas estratégias:
1. COPY FROM STDIN (bulk load inicial): 10-50x mais rápido que INSERT
2. execute_values com ON CONFLICT DO UPDATE (atualização incremental)
"""
import io
import uuid
from contextlib import contextmanager
from typing import Generator

import polars as pl
import psycopg2
import psycopg2.extras
from loguru import logger

from config import settings

ACTIVE_CNPJ_FILTER_TABLE = "etl_active_cnpjs"


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


def rebuild_active_cnpj_filter(conn: psycopg2.extensions.connection) -> int:
    """
    Rebuilds the transient active-company filter used by active-only ETL loads.

    The table is UNLOGGED because it is derived from `estabelecimentos` and only
    exists to filter the current load. This avoids WAL overhead while letting
    parallel ETL connections join against the same active CNPJ set.
    """
    with conn.cursor() as cur:
        cur.execute(f"DROP TABLE IF EXISTS {ACTIVE_CNPJ_FILTER_TABLE}")
        cur.execute(
            f"""
            CREATE UNLOGGED TABLE {ACTIVE_CNPJ_FILTER_TABLE} AS
            SELECT DISTINCT cnpj_basico
            FROM estabelecimentos
            WHERE situacao_cadastral = 2
            """
        )
        cur.execute(
            f"ALTER TABLE {ACTIVE_CNPJ_FILTER_TABLE} "
            f"ADD PRIMARY KEY (cnpj_basico)"
        )
        cur.execute(f"ANALYZE {ACTIVE_CNPJ_FILTER_TABLE}")
        cur.execute(f"SELECT count(*) FROM {ACTIVE_CNPJ_FILTER_TABLE}")
        total = int(cur.fetchone()[0])
    conn.commit()
    logger.success(f"Active CNPJ filter rebuilt: {total:,} cnpj_basico values")
    return total


def drop_active_cnpj_filter(conn: psycopg2.extensions.connection) -> None:
    """Drops the transient active-company filter to release disk after full-load."""
    with conn.cursor() as cur:
        cur.execute(f"DROP TABLE IF EXISTS {ACTIVE_CNPJ_FILTER_TABLE}")
    conn.commit()
    logger.info(f"Dropped transient table {ACTIVE_CNPJ_FILTER_TABLE}")


def bulk_copy_active_filtered(
    conn: psycopg2.extensions.connection,
    df: pl.DataFrame,
    table: str,
    columns: list[str],
    conflict_columns: list[str] | None = None,
    commit: bool = False,
) -> int:
    """
    Loads a batch through a temp staging table and keeps only active CNPJ bases.

    This avoids holding tens of millions of CNPJ keys in Python memory and avoids
    inserting dead RF data into the final tables. Intended for empresas, simples
    and socios after `rebuild_active_cnpj_filter()` has run.
    """
    if len(df) == 0:
        return 0

    available_cols = [c for c in columns if c in df.columns]
    if "cnpj_basico" not in available_cols:
        raise ValueError(f"{table} cannot be active-filtered without cnpj_basico")

    staging_table = f"_etl_stage_{table}_{uuid.uuid4().hex}"
    columns_sql = ", ".join(available_cols)
    select_sql = ", ".join(f"s.{c}" for c in available_cols)

    sql = (
        f"INSERT INTO {table} ({columns_sql}) "
        f"SELECT {select_sql} "
        f"FROM {staging_table} s "
        f"JOIN {ACTIVE_CNPJ_FILTER_TABLE} a ON a.cnpj_basico = s.cnpj_basico"
    )

    conflict_columns = conflict_columns or []
    if conflict_columns:
        update_cols = [c for c in available_cols if c not in conflict_columns]
        if update_cols:
            update_clause = ", ".join(f"{c} = EXCLUDED.{c}" for c in update_cols)
            sql += (
                f" ON CONFLICT ({', '.join(conflict_columns)}) "
                f"DO UPDATE SET {update_clause}"
            )
        else:
            sql += f" ON CONFLICT ({', '.join(conflict_columns)}) DO NOTHING"

    with conn.cursor() as cur:
        cur.execute(f"CREATE TEMP TABLE {staging_table} (LIKE {table} INCLUDING DEFAULTS) ON COMMIT DROP")
        bulk_copy(conn, df, staging_table, available_cols)
        cur.execute(sql)
        loaded = cur.rowcount
        cur.execute(f"DROP TABLE {staging_table}")

    if commit:
        conn.commit()

    logger.debug(f"ACTIVE FILTER {loaded:,}/{len(df):,} rows → {table}")
    return loaded


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
