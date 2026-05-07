-- CNPJ Discovery - Indexes for advanced filter support (v2)

CREATE EXTENSION IF NOT EXISTS pg_trgm;

CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_estab_bairro_trgm
    ON estabelecimentos USING GIN (bairro gin_trgm_ops);

CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_estab_data_inicio
    ON estabelecimentos (data_inicio);

CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_estab_matriz_filial
    ON estabelecimentos (matriz_filial);

CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_empresas_natureza
    ON empresas (natureza_juridica);

CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_simples_opcao
    ON simples (opcao_simples);
