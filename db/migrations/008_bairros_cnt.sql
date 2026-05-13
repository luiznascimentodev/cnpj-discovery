-- Rebuilds bairros_lookup with a cnt column (number of establishments per canonical bairro).
-- cnt is used in the API query to score bairros: score = len - LN(cnt+1).
-- This makes high-frequency spellings beat rare typos even when the typo is 1 char shorter
-- (e.g. "SITIO CERCAO"×5 loses to "SITIO CERCADO"×50000 even though it is shorter).

DROP MATERIALIZED VIEW IF EXISTS bairros_lookup CASCADE;

CREATE MATERIALIZED VIEW bairros_lookup AS
WITH normalized AS (
    SELECT
        est.uf,
        est.municipio,
        trim(regexp_replace(
            regexp_replace(
                regexp_replace(upper(est.bairro), E'^[^A-Z0-9]+', ''),
                E'^([A-Z0-9]{1,3}[\\-.:])+', ''
            ),
            E'\\s+', ' ', 'g'
        )) AS bairro_canonical
    FROM estabelecimentos est
    WHERE est.uf IS NOT NULL
      AND est.bairro IS NOT NULL
      AND est.bairro != ''
)
SELECT
    n.uf,
    n.municipio,
    m.descricao AS municipio_descricao,
    n.bairro_canonical,
    COUNT(*) AS cnt
FROM normalized n
JOIN municipios m ON m.codigo = n.municipio
WHERE length(n.bairro_canonical) >= 2
GROUP BY n.uf, n.municipio, m.descricao, n.bairro_canonical
ORDER BY n.uf, n.bairro_canonical, m.descricao;

CREATE UNIQUE INDEX idx_bairros_lookup_unique
    ON bairros_lookup (uf, municipio, bairro_canonical);

CREATE INDEX idx_bairros_lookup_trgm
    ON bairros_lookup USING gin (bairro_canonical gin_trgm_ops);
