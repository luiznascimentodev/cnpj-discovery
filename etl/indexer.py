"""
Indexer ETL — gerenciamento de índices do PostgreSQL durante carga massiva.

Estratégia de performance:
- DROP índices antes da carga inicial (exceto PKs)
- CREATE INDEX CONCURRENTLY após a carga (não bloqueia leituras)
"""
import psycopg2
from loguru import logger

from config import settings
from loader import get_connection

# Definição dos índices gerenciados pelo ETL.
# Cada entrada: (nome_do_índice, SQL de criação)
# CREATE INDEX CONCURRENTLY não pode rodar dentro de transação,
# por isso cada índice é commitado separadamente.
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
]


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


def create_managed_indexes(conn: psycopg2.extensions.connection) -> int:
    """
    Recria todos os índices gerenciados após a carga.

    Usa CREATE INDEX CONCURRENTLY para não bloquear leituras durante a criação.
    CONCURRENTLY requer autocommit (não pode estar dentro de transação).

    A conexão recebida é usada apenas para obter o DSN. Uma conexão auxiliar
    dedicada em modo autocommit é aberta internamente, pois psycopg2 pode
    manter estado de transação implícita que impede o uso de CONCURRENTLY
    mesmo após setar autocommit=True na conexão original.

    Returns:
        Número de índices criados
    """
    created = 0

    # Abre nova conexão em autocommit puro — sem nenhum histórico de transação.
    # CONCURRENTLY exige que a sessão não tenha transação ativa.
    # Usamos settings.dsn para obter o DSN completo (com senha), pois
    # psycopg2 redacta a senha em conn.dsn.
    ac_conn = psycopg2.connect(settings.dsn)
    ac_conn.autocommit = True

    try:
        with ac_conn.cursor() as cur:
            for name, sql in MANAGED_INDEXES:
                logger.info(f"Creating index {name}...")
                cur.execute(sql)
                created += 1
                logger.success(f"Index {name} created")
    finally:
        ac_conn.close()

    logger.success(f"Created {created} managed indexes")
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
