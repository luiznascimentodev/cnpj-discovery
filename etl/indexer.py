"""
Indexer ETL — gerenciamento de índices do PostgreSQL durante carga massiva.

Estratégia de performance:
- DROP índices antes da carga inicial (exceto PKs)
- CREATE INDEX CONCURRENTLY em paralelo após a carga
  - Cada índice roda em thread própria com conexão autocommit dedicada
  - maintenance_work_mem alto reduz sorts em disco
  - max_parallel_maintenance_workers usa múltiplos cores por índice
"""
import re
import time
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor, as_completed

import psycopg2
from psycopg2 import errors
from loguru import logger

from config import settings
from loader import get_connection

# Definição dos índices gerenciados pelo ETL.
# Cada entrada: (nome_do_índice, SQL de criação)
# CREATE INDEX CONCURRENTLY não pode rodar dentro de transação,
# por isso cada índice usa sua própria conexão em autocommit.
MANAGED_INDEXES: list[tuple[str, str]] = [
    (
        "idx_estab_cnpj_basico",
        "CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_estab_cnpj_basico "
        "ON estabelecimentos (cnpj_basico)",
    ),
    (
        "idx_socios_cnpj_basico",
        "CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_socios_cnpj_basico "
        "ON socios (cnpj_basico)",
    ),
    (
        "idx_simples_cnpj_basico",
        "CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_simples_cnpj_basico "
        "ON simples (cnpj_basico)",
    ),
    (
        "idx_estab_uf_cnae_sit",
        "CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_estab_uf_cnae_sit "
        "ON estabelecimentos (uf, cnae_principal, situacao_cadastral)",
    ),
    (
        "idx_estab_municipio_sit",
        "CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_estab_municipio_sit "
        "ON estabelecimentos (municipio, situacao_cadastral)",
    ),
    (
        "idx_estab_situacao",
        "CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_estab_situacao "
        "ON estabelecimentos (situacao_cadastral)",
    ),
    (
        "idx_empresas_porte",
        "CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_empresas_porte "
        "ON empresas (porte)",
    ),
    (
        "idx_empresas_capital",
        "CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_empresas_capital "
        "ON empresas (capital_social)",
    ),
    (
        "idx_estab_uf",
        "CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_estab_uf "
        "ON estabelecimentos (uf)",
    ),
    (
        "idx_estab_cursor",
        "CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_estab_cursor "
        "ON estabelecimentos (cnpj_basico, cnpj_ordem)",
    ),
    (
        "idx_estab_fts_fantasia",
        "CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_estab_fts_fantasia "
        "ON estabelecimentos USING GIN "
        "(to_tsvector('portuguese', coalesce(nome_fantasia, '')))",
    ),
    (
        "idx_empresas_fts_razao",
        "CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_empresas_fts_razao "
        "ON empresas USING GIN "
        "(to_tsvector('portuguese', razao_social))",
    ),
    (
        "idx_estab_ativas_uf",
        "CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_estab_ativas_uf "
        "ON estabelecimentos (uf, cnpj_basico, cnpj_ordem) "
        "WHERE situacao_cadastral = 2",
    ),
    (
        "idx_estab_bairro_trgm",
        "CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_estab_bairro_trgm "
        "ON estabelecimentos USING GIN (bairro gin_trgm_ops)",
    ),
    (
        "idx_estab_data_inicio",
        "CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_estab_data_inicio "
        "ON estabelecimentos (data_inicio)",
    ),
    (
        "idx_estab_matriz_filial",
        "CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_estab_matriz_filial "
        "ON estabelecimentos (matriz_filial)",
    ),
    (
        "idx_simples_opcao",
        "CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_simples_opcao "
        "ON simples (opcao_simples)",
    ),
    (
        "idx_estab_active_cnae_cursor",
        "CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_estab_active_cnae_cursor "
        "ON estabelecimentos (cnae_principal, cnpj_basico, cnpj_ordem) "
        "WHERE situacao_cadastral = 2",
    ),
    (
        "idx_estab_active_uf_cnae_cursor",
        "CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_estab_active_uf_cnae_cursor "
        "ON estabelecimentos (uf, cnae_principal, cnpj_basico, cnpj_ordem) "
        "WHERE situacao_cadastral = 2",
    ),
    (
        "idx_estab_active_municipio_cursor",
        "CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_estab_active_municipio_cursor "
        "ON estabelecimentos (municipio, cnpj_basico, cnpj_ordem) "
        "WHERE situacao_cadastral = 2",
    ),
    (
        "idx_estab_active_matriz_cursor",
        "CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_estab_active_matriz_cursor "
        "ON estabelecimentos (matriz_filial, cnpj_basico, cnpj_ordem) "
        "WHERE situacao_cadastral = 2",
    ),
    (
        "idx_estab_active_data_cursor",
        "CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_estab_active_data_cursor "
        "ON estabelecimentos (data_inicio, cnpj_basico, cnpj_ordem) "
        "WHERE situacao_cadastral = 2",
    ),
    (
        "idx_estab_active_uf_bairro_canonical_cursor",
        "CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_estab_active_uf_bairro_canonical_cursor "
        "ON estabelecimentos ("
        "uf, "
        "trim(regexp_replace("
        "regexp_replace("
        "regexp_replace(upper(bairro), E'^[^A-Z0-9]+', ''), "
        "E'^([A-Z0-9]{1,3}[\\\\-.:])+', ''"
        "), "
        "E'\\\\s+', ' ', 'g'"
        ")), "
        "cnpj_basico, "
        "cnpj_ordem"
        ") "
        "WHERE situacao_cadastral = 2 AND bairro IS NOT NULL AND bairro != ''",
    ),
]

# Configurações de sessão para builds de índice mais rápidos.
# maintenance_work_mem: mais RAM = menos sorts em disco durante o build.
# max_parallel_maintenance_workers: cores usados por cada build de índice.
_INDEX_SESSION_SETTINGS = """
    SET maintenance_work_mem = '512MB';
    SET max_parallel_maintenance_workers = 2;
"""


def drop_managed_indexes(conn: psycopg2.extensions.connection) -> int:
    """
    Remove todos os índices gerenciados (exceto PKs).

    Chamado antes da carga inicial para máxima velocidade de COPY.
    PKs não são removidas — o PostgreSQL as exige para integridade básica.

    Returns:
        Número de índices removidos
    """
    names = [name for name, _ in MANAGED_INDEXES]
    dropped = 0
    with conn.cursor() as cur:
        for name in names:
            cur.execute(f"DROP INDEX IF EXISTS {name}")
            dropped += 1
    conn.commit()
    logger.info(f"Dropped {dropped} managed indexes")
    return dropped


def _build_index(name: str, sql: str, max_retries: int = 3) -> float:
    """Cria um único índice em conexão dedicada com autocommit. Retorna tempo em segundos."""
    for attempt in range(1, max_retries + 1):
        start = time.monotonic()
        conn = psycopg2.connect(settings.dsn)
        conn.autocommit = True
        try:
            with conn.cursor() as cur:
                cur.execute(_INDEX_SESSION_SETTINGS)
                logger.info(f"Creating index {name} (attempt {attempt}/{max_retries})...")
                cur.execute(sql)
            elapsed = time.monotonic() - start
            logger.success(f"Index {name} created in {elapsed:.0f}s")
            return elapsed
        except errors.DeadlockDetected as exc:
            logger.warning(f"Deadlock detected for index {name} on attempt {attempt}: {exc}")
            if attempt == max_retries:
                raise
            time.sleep(attempt * 5)  # Backoff exponencial simples
        except Exception:
            raise
        finally:
            conn.close()
    return 0.0  # Should not reach here


def create_managed_indexes(conn: psycopg2.extensions.connection) -> int:
    """
    Recria todos os índices gerenciados após a carga em paralelo.

    Usa CREATE INDEX CONCURRENTLY (não bloqueia leituras) com múltiplas threads.
    Estratégia: Agrupa índices por tabela e processa cada tabela em sua própria thread.
    Isso evita deadlocks entre múltiplos CREATE INDEX CONCURRENTLY na mesma tabela,
    mantendo paralelismo entre tabelas diferentes.

    etl_index_workers controla o número máximo de tabelas processadas simultaneamente.

    Returns:
        Número de índices criados com sucesso
    """
    # Agrupa índices por tabela
    by_table = defaultdict(list)
    for name, sql in MANAGED_INDEXES:
        # Extrai nome da tabela do SQL: "ON <tabela> ("
        match = re.search(r"ON\s+(\w+)", sql, re.IGNORECASE)
        table = match.group(1) if match else "unknown"
        by_table[table].append((name, sql))

    n_workers = min(settings.etl_index_workers, len(by_table))
    logger.info(
        f"Creating {len(MANAGED_INDEXES)} indexes across {len(by_table)} tables "
        f"with {n_workers} parallel workers."
    )

    created = 0
    failed: list[str] = []

    def _build_indexes_for_table(table_name: str, indexes: list[tuple[str, str]]) -> int:
        table_created = 0
        for name, sql in indexes:
            try:
                _build_index(name, sql)
                table_created += 1
            except Exception as exc:
                logger.error(f"Failed to create index {name} on table {table_name}: {exc}")
                failed.append(name)
        return table_created

    with ThreadPoolExecutor(max_workers=n_workers) as executor:
        futures = {
            executor.submit(_build_indexes_for_table, table, idxs): table
            for table, idxs in by_table.items()
        }
        for future in as_completed(futures):
            created += future.result()

    if failed:
        logger.warning(f"Failed indexes: {', '.join(failed)}")

    logger.success(f"Created {created}/{len(MANAGED_INDEXES)} managed indexes")
    return created


def get_existing_indexes(conn: psycopg2.extensions.connection) -> set[str]:
    """
    Retorna set com nomes dos índices que existem no banco.
    Útil para verificar o estado atual antes de dropar/criar.
    """
    managed_names = tuple(name for name, _ in MANAGED_INDEXES)
    with conn.cursor() as cur:
        cur.execute(
            "SELECT indexname FROM pg_indexes "
            "WHERE schemaname = 'public' AND indexname = ANY(%s)",
            (list(managed_names),),
        )
        return {row[0] for row in cur.fetchall()}
