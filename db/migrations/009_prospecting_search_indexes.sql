-- CNPJ Discovery - Prospecting search indexes
-- Aligns common filters with keyset pagination so the API can find the first
-- 100 candidate establishments before hydrating join-only display columns.

CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_estab_active_cnae_cursor
    ON estabelecimentos (cnae_principal, cnpj_basico, cnpj_ordem)
    WHERE situacao_cadastral = 2;

CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_estab_active_uf_cnae_cursor
    ON estabelecimentos (uf, cnae_principal, cnpj_basico, cnpj_ordem)
    WHERE situacao_cadastral = 2;

CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_estab_active_municipio_cursor
    ON estabelecimentos (municipio, cnpj_basico, cnpj_ordem)
    WHERE situacao_cadastral = 2;

CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_estab_active_matriz_cursor
    ON estabelecimentos (matriz_filial, cnpj_basico, cnpj_ordem)
    WHERE situacao_cadastral = 2;

CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_estab_active_data_cursor
    ON estabelecimentos (data_inicio, cnpj_basico, cnpj_ordem)
    WHERE situacao_cadastral = 2;

CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_estab_active_uf_bairro_canonical_cursor
    ON estabelecimentos (
        uf,
        trim(regexp_replace(
            regexp_replace(
                regexp_replace(upper(bairro), E'^[^A-Z0-9]+', ''),
                E'^([A-Z0-9]{1,3}[\\-.:])+', ''
            ),
            E'\\s+', ' ', 'g'
        )),
        cnpj_basico,
        cnpj_ordem
    )
    WHERE situacao_cadastral = 2 AND bairro IS NOT NULL AND bairro != '';
