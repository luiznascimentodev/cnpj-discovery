"""Worker heartbeat: persists alive signal to worker_heartbeats table.

Workers call `beat()` every loop iteration. Operations can query the table
to find stuck workers and trigger recovery.
"""
from __future__ import annotations

import os
import socket

_SQL_UPSERT_HEARTBEAT = """
    INSERT INTO paid_enrichment.worker_heartbeats (
        worker_id, role, hostname, pid, current_stage, current_job_id,
        started_at, heartbeat_at, metadata
    )
    VALUES ($1, $2, $3, $4, $5, $6, now(), now(), $7::jsonb)
    ON CONFLICT (worker_id) DO UPDATE SET
        current_stage  = EXCLUDED.current_stage,
        current_job_id = EXCLUDED.current_job_id,
        heartbeat_at   = now(),
        metadata       = EXCLUDED.metadata
"""

_SQL_DELETE_HEARTBEAT = """
    DELETE FROM paid_enrichment.worker_heartbeats WHERE worker_id = $1
"""


async def beat(
    pool,
    *,
    worker_id: str,
    role: str,
    current_stage: str | None = None,
    current_job_id: int | None = None,
    metadata: dict | None = None,
) -> None:
    import json
    async with pool.acquire() as conn:
        await conn.execute(
            _SQL_UPSERT_HEARTBEAT,
            worker_id,
            role,
            socket.gethostname(),
            os.getpid(),
            current_stage,
            current_job_id,
            json.dumps(metadata or {}),
        )


async def remove(pool, *, worker_id: str) -> None:
    async with pool.acquire() as conn:
        await conn.execute(_SQL_DELETE_HEARTBEAT, worker_id)
