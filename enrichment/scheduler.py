"""Scheduler com resume real para o pipeline de enriquecimento.

Duas camadas de resume:

1. Cursor de seed (`paid_enrichment.enrichment_seed_cursor`):
   guarda o último `(cnpj_basico, cnpj_ordem, cnpj_dv)` percorrido em
   `estabelecimentos` para cada `reason`. Cada nova chamada de
   `seed_active_targets` continua de onde a última parou — nunca varre
   a tabela inteira do começo.

2. Fila persistente (`paid_enrichment.enrichment_targets`):
   `status + next_run_at + locked_at`. `claim_targets` usa
   `FOR UPDATE SKIP LOCKED` mais um *lease*. Workers concorrentes não
   pegam o mesmo target, e workers que travam liberam o lease
   automaticamente quando ele expira (recuperação de crash).
"""
from dataclasses import dataclass

DEFAULT_LEASE_SECONDS = 300
DEFAULT_SEED_BATCH = 1000
DEFAULT_CLAIM_BATCH = 50

VALID_TARGET_STATUSES = frozenset(
    {"pending", "running", "done", "retry", "blocked", "error"}
)

_SQL_GET_CURSOR = """
    SELECT last_cnpj_basico, last_cnpj_ordem, last_cnpj_dv, rows_seeded
    FROM paid_enrichment.enrichment_seed_cursor
    WHERE reason = $1
"""

_SQL_UPSERT_CURSOR = """
    INSERT INTO paid_enrichment.enrichment_seed_cursor (
        reason, last_cnpj_basico, last_cnpj_ordem, last_cnpj_dv, rows_seeded, last_run_at, updated_at
    )
    VALUES ($1, $2, $3, $4, $5, now(), now())
    ON CONFLICT (reason) DO UPDATE SET
        last_cnpj_basico = EXCLUDED.last_cnpj_basico,
        last_cnpj_ordem = EXCLUDED.last_cnpj_ordem,
        last_cnpj_dv = EXCLUDED.last_cnpj_dv,
        rows_seeded = paid_enrichment.enrichment_seed_cursor.rows_seeded + EXCLUDED.rows_seeded,
        last_run_at = now(),
        updated_at = now()
"""

_SQL_SELECT_NEW_ROWS = """
    SELECT est.cnpj_basico, est.cnpj_ordem, est.cnpj_dv
    FROM estabelecimentos est
    WHERE est.situacao_cadastral = 2
      AND (est.cnpj_basico, est.cnpj_ordem, est.cnpj_dv) > ($1, $2, $3)
      AND (
            COALESCE(est.email, '') = ''
         OR (COALESCE(est.telefone1, '') = '' AND COALESCE(est.telefone2, '') = '')
      )
    ORDER BY est.cnpj_basico, est.cnpj_ordem, est.cnpj_dv
    LIMIT $4
"""

_SQL_INSERT_TARGET = """
    INSERT INTO paid_enrichment.enrichment_targets (
        cnpj_basico, cnpj_ordem, cnpj_dv, priority, status, reason, next_run_at, updated_at
    )
    VALUES ($1, $2, $3, $4, 'pending', $5, now(), now())
    ON CONFLICT (cnpj_basico, cnpj_ordem, cnpj_dv, reason) DO NOTHING
"""

_SQL_CLAIM_TARGETS = """
    WITH due AS (
        SELECT id
        FROM paid_enrichment.enrichment_targets
        WHERE status IN ('pending', 'retry')
          AND next_run_at <= now()
          AND (locked_at IS NULL OR locked_at < now() - make_interval(secs => $2))
        ORDER BY priority DESC, next_run_at, id
        LIMIT $3
        FOR UPDATE SKIP LOCKED
    )
    UPDATE paid_enrichment.enrichment_targets t
    SET status = 'running',
        locked_at = now(),
        locked_by = $1,
        attempts = t.attempts + 1,
        updated_at = now()
    FROM due
    WHERE t.id = due.id
    RETURNING t.id, t.cnpj_basico, t.cnpj_ordem, t.cnpj_dv, t.reason, t.attempts, t.priority
"""

_SQL_COMPLETE_TARGET = """
    UPDATE paid_enrichment.enrichment_targets
    SET status = $2,
        next_run_at = now() + make_interval(secs => $3),
        last_error = $4,
        locked_at = NULL,
        locked_by = NULL,
        updated_at = now()
    WHERE id = $1
"""

_SQL_RELEASE_STALE = """
    UPDATE paid_enrichment.enrichment_targets
    SET status = 'pending',
        locked_at = NULL,
        locked_by = NULL,
        updated_at = now()
    WHERE status = 'running'
      AND locked_at IS NOT NULL
      AND locked_at < now() - make_interval(secs => $1)
    RETURNING id
"""


@dataclass(frozen=True)
class CursorState:
    last_cnpj_basico: str
    last_cnpj_ordem: str
    last_cnpj_dv: str
    rows_seeded: int


@dataclass(frozen=True)
class ClaimedTarget:
    id: int
    cnpj_basico: str
    cnpj_ordem: str
    cnpj_dv: str
    reason: str
    attempts: int
    priority: int


async def get_cursor(pool, reason: str) -> CursorState:
    async with pool.acquire() as conn:
        row = await conn.fetchrow(_SQL_GET_CURSOR, reason)
    if not row:
        return CursorState("00000000", "0000", "00", 0)
    return CursorState(
        last_cnpj_basico=row["last_cnpj_basico"],
        last_cnpj_ordem=row["last_cnpj_ordem"],
        last_cnpj_dv=row["last_cnpj_dv"],
        rows_seeded=row["rows_seeded"],
    )


async def seed_active_targets(
    pool,
    *,
    reason: str = "missing_contacts",
    priority: int = 50,
    batch_size: int = DEFAULT_SEED_BATCH,
) -> int:
    """Resume-aware: avança a partir do cursor persistido em `reason`.

    Retorna o número de linhas RF lidas no lote (independente de quantos
    targets foram efetivamente inseridos — `ON CONFLICT DO NOTHING` ignora
    duplicatas mas o cursor sempre avança).
    """
    if batch_size <= 0:
        raise ValueError("batch_size must be positive")

    async with pool.acquire() as conn:
        cursor_row = await conn.fetchrow(_SQL_GET_CURSOR, reason)
        if cursor_row:
            last_basico = cursor_row["last_cnpj_basico"]
            last_ordem = cursor_row["last_cnpj_ordem"]
            last_dv = cursor_row["last_cnpj_dv"]
        else:
            last_basico, last_ordem, last_dv = "00000000", "0000", "00"

        rows = await conn.fetch(
            _SQL_SELECT_NEW_ROWS,
            last_basico,
            last_ordem,
            last_dv,
            batch_size,
        )
        if not rows:
            return 0

        records = [
            (row["cnpj_basico"], row["cnpj_ordem"], row["cnpj_dv"], priority, reason)
            for row in rows
        ]
        last = rows[-1]
        async with conn.transaction():
            await conn.executemany(_SQL_INSERT_TARGET, records)
            await conn.execute(
                _SQL_UPSERT_CURSOR,
                reason,
                last["cnpj_basico"],
                last["cnpj_ordem"],
                last["cnpj_dv"],
                len(rows),
            )
    return len(rows)


async def claim_targets(
    pool,
    *,
    worker_id: str,
    batch_size: int = DEFAULT_CLAIM_BATCH,
    lease_seconds: int = DEFAULT_LEASE_SECONDS,
) -> list[ClaimedTarget]:
    if not worker_id:
        raise ValueError("worker_id is required")
    if batch_size <= 0:
        raise ValueError("batch_size must be positive")
    async with pool.acquire() as conn:
        rows = await conn.fetch(
            _SQL_CLAIM_TARGETS,
            worker_id,
            lease_seconds,
            batch_size,
        )
    return [
        ClaimedTarget(
            id=row["id"],
            cnpj_basico=row["cnpj_basico"],
            cnpj_ordem=row["cnpj_ordem"],
            cnpj_dv=row["cnpj_dv"],
            reason=row["reason"],
            attempts=row["attempts"],
            priority=row["priority"],
        )
        for row in rows
    ]


async def complete_target(
    pool,
    *,
    target_id: int,
    status: str,
    retry_in_seconds: int = 0,
    last_error: str | None = None,
) -> None:
    if status not in VALID_TARGET_STATUSES:
        raise ValueError(f"Invalid target status: {status}")
    delay = max(retry_in_seconds, 0)
    async with pool.acquire() as conn:
        await conn.execute(
            _SQL_COMPLETE_TARGET,
            target_id,
            status,
            delay,
            last_error,
        )


async def release_stale_locks(
    pool,
    *,
    lease_seconds: int = DEFAULT_LEASE_SECONDS,
) -> int:
    async with pool.acquire() as conn:
        rows = await conn.fetch(_SQL_RELEASE_STALE, lease_seconds)
    return len(rows)
