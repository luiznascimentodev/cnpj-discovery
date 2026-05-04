"""
State manager ETL — controla o estado de processamento de cada arquivo da RF.

A tabela etl_state registra qual arquivo foi processado, quando, e seu status.
Isso permite retomar a carga de onde parou e detectar arquivos novos/atualizados.
"""
from datetime import datetime, timezone
from typing import Optional

import psycopg2
from loguru import logger


class ETLFileState:
    """Representa o estado de um arquivo RF na tabela etl_state."""
    def __init__(
        self,
        arquivo: str,
        status: str,
        last_modified: Optional[datetime] = None,
        loaded_at: Optional[datetime] = None,
        rows_processed: int = 0,
        error_message: Optional[str] = None,
    ):
        self.arquivo = arquivo
        self.status = status
        self.last_modified = last_modified
        self.loaded_at = loaded_at
        self.rows_processed = rows_processed
        self.error_message = error_message


def get_file_state(
    conn: psycopg2.extensions.connection,
    filename: str,
) -> Optional[ETLFileState]:
    """
    Busca o estado atual de um arquivo na tabela etl_state.
    Retorna None se o arquivo nunca foi processado.
    """
    with conn.cursor() as cur:
        cur.execute(
            "SELECT arquivo, status, last_modified, loaded_at, rows_processed, error_message "
            "FROM etl_state WHERE arquivo = %s",
            (filename,),
        )
        row = cur.fetchone()
    if row is None:
        return None
    return ETLFileState(
        arquivo=row[0],
        status=row[1],
        last_modified=row[2],
        loaded_at=row[3],
        rows_processed=row[4] or 0,
        error_message=row[5],
    )


def set_file_state(
    conn: psycopg2.extensions.connection,
    filename: str,
    status: str,
    last_modified: Optional[datetime] = None,
    rows_processed: int = 0,
    error_message: Optional[str] = None,
) -> None:
    """
    Insere ou atualiza o estado de um arquivo na tabela etl_state.
    Usa ON CONFLICT DO UPDATE para ser idempotente.
    """
    now = datetime.now(timezone.utc)
    with conn.cursor() as cur:
        cur.execute(
            """
            INSERT INTO etl_state
                (arquivo, status, last_modified, loaded_at, rows_processed, error_message)
            VALUES (%s, %s, %s, %s, %s, %s)
            ON CONFLICT (arquivo) DO UPDATE SET
                status = EXCLUDED.status,
                last_modified = EXCLUDED.last_modified,
                loaded_at = EXCLUDED.loaded_at,
                rows_processed = EXCLUDED.rows_processed,
                error_message = EXCLUDED.error_message
            """,
            (filename, status, last_modified, now, rows_processed, error_message),
        )
    conn.commit()
    logger.debug(f"State updated: {filename} → {status}")


def needs_update(
    conn: psycopg2.extensions.connection,
    filename: str,
    remote_last_modified: datetime,
) -> bool:
    """
    Determina se um arquivo precisa ser (re)processado.

    Retorna True se:
    - Arquivo nunca foi processado (não existe em etl_state)
    - Status anterior é 'error' (reprocessar após falha)
    - Status anterior é 'pending' ou 'downloading' ou 'loading' (interrompido)
    - remote_last_modified é mais recente que last_modified no banco
    """
    state = get_file_state(conn, filename)
    if state is None:
        return True
    if state.status != "done":
        return True
    if state.last_modified is None:
        return True
    # Normalizar timezone para comparação
    remote = remote_last_modified
    local = state.last_modified
    if remote.tzinfo is None:
        remote = remote.replace(tzinfo=timezone.utc)
    if local.tzinfo is None:
        local = local.replace(tzinfo=timezone.utc)
    return remote > local


def get_all_states(
    conn: psycopg2.extensions.connection,
) -> list[ETLFileState]:
    """Retorna todos os estados registrados, ordenados por loaded_at DESC."""
    with conn.cursor() as cur:
        cur.execute(
            "SELECT arquivo, status, last_modified, loaded_at, rows_processed, error_message "
            "FROM etl_state ORDER BY loaded_at DESC NULLS LAST"
        )
        rows = cur.fetchall()
    return [
        ETLFileState(
            arquivo=r[0], status=r[1], last_modified=r[2],
            loaded_at=r[3], rows_processed=r[4] or 0, error_message=r[5],
        )
        for r in rows
    ]
