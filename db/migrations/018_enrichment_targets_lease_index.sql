-- CNPJ Discovery — Índice parcial dedicado à query de lease do enrichment worker.
--
-- A query em enrichment/scheduler.py (_SQL_CLAIM_TARGETS) faz:
--   WHERE status IN ('pending','retry') AND next_run_at <= now() AND (...)
--   ORDER BY priority DESC, next_run_at, id
--   LIMIT $3 FOR UPDATE SKIP LOCKED
--
-- O índice anterior (status, next_run_at, priority DESC) não casava com o
-- ORDER BY e forçava Seq Scan + Sort externo de 14M linhas / 536 MB em disco
-- (~20s por chamada). Com 10+ workers em paralelo, o Postgres saturava CPU.
--
-- Este índice parcial:
--  - Cobre só status pending/retry (~98% da tabela hoje, mas predicado claro)
--  - Tem mesma ordem do ORDER BY → sem Sort
--  - Permite IndexScan + LIMIT imediato (sub-millis)
--
-- IF NOT EXISTS garante idempotência quando aplicado manualmente fora do
-- runner. CREATE INDEX CONCURRENTLY não pode rodar em transação, então este
-- arquivo é aplicado a mão antes de ser registrado em schema_migrations.

CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_enrichment_targets_lease_ready
    ON paid_enrichment.enrichment_targets (priority DESC, next_run_at, id)
    WHERE status IN ('pending', 'retry');
