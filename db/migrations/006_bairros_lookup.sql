-- Materialized view de bairros únicos por UF para autocomplete rápido.
-- Evita DISTINCT scan em 50M+ linhas de estabelecimentos a cada request.
-- Refresh: executar REFRESH MATERIALIZED VIEW CONCURRENTLY bairros_lookup após cada ETL.

CREATE MATERIALIZED VIEW IF NOT EXISTS bairros_lookup AS
SELECT DISTINCT uf, bairro
FROM estabelecimentos
WHERE uf IS NOT NULL
  AND bairro IS NOT NULL
  AND bairro != ''
ORDER BY uf, bairro;

CREATE UNIQUE INDEX IF NOT EXISTS idx_bairros_lookup_uf_bairro
    ON bairros_lookup (uf, bairro);

CREATE INDEX IF NOT EXISTS idx_bairros_lookup_bairro_trgm
    ON bairros_lookup USING gin (bairro gin_trgm_ops);
