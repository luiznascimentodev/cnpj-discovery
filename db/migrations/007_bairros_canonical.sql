-- Rebuilds bairros_lookup with normalized canonical names and municipality info.
-- Normalization pipeline (applied in order):
--   1. Uppercase
--   2. Strip leading non-alphanumeric chars  (*CENTRO → CENTRO, .CENTRO → CENTRO)
--   3. Strip district code prefixes of form X- or X.X- (B-N.C-SITIO → SITIO CERCADO)
--   4. Collapse whitespace
-- Unique per (uf, municipio, bairro_canonical).
-- Refresh after each ETL: REFRESH MATERIALIZED VIEW CONCURRENTLY bairros_lookup;

DROP MATERIALIZED VIEW IF EXISTS bairros_lookup;

CREATE MATERIALIZED VIEW bairros_lookup AS
SELECT DISTINCT
    est.uf,
    est.municipio,
    m.descricao AS municipio_descricao,
    trim(regexp_replace(
        regexp_replace(
            regexp_replace(upper(est.bairro), E'^[^A-Z0-9]+', ''),
            E'^([A-Z0-9]{1,3}[\\-.:])+', ''
        ),
        E'\\s+', ' ', 'g'
    )) AS bairro_canonical
FROM estabelecimentos est
JOIN municipios m ON m.codigo = est.municipio
WHERE est.uf IS NOT NULL
  AND est.bairro IS NOT NULL
  AND est.bairro != ''
  AND length(trim(regexp_replace(
        regexp_replace(
            regexp_replace(upper(est.bairro), E'^[^A-Z0-9]+', ''),
            E'^([A-Z0-9]{1,3}[\\-.:])+', ''
        ),
        E'\\s+', ' ', 'g'
      ))) >= 2
ORDER BY uf, bairro_canonical, municipio_descricao;

CREATE UNIQUE INDEX idx_bairros_lookup_unique
    ON bairros_lookup (uf, municipio, bairro_canonical);

CREATE INDEX idx_bairros_lookup_trgm
    ON bairros_lookup USING gin (bairro_canonical gin_trgm_ops);
