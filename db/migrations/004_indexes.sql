-- CNPJ Discovery - Índices de Performance
-- ATENÇÃO: Este arquivo cria os índices iniciais.
-- O ETL pode dropar e recriar estes índices durante carga massiva.
-- Usar CREATE INDEX CONCURRENTLY não é permitido dentro de transação,
-- então o ETL os cria diretamente via Python após a carga.

-- FK implícita (sem constraint formal para performance de load)
CREATE INDEX IF NOT EXISTS idx_estab_cnpj_basico     ON estabelecimentos (cnpj_basico);
CREATE INDEX IF NOT EXISTS idx_socios_cnpj_basico     ON socios (cnpj_basico);
CREATE INDEX IF NOT EXISTS idx_simples_cnpj_basico    ON simples (cnpj_basico);

-- Filtros de busca mais comuns
CREATE INDEX IF NOT EXISTS idx_estab_uf_cnae_sit      ON estabelecimentos (uf, cnae_principal, situacao_cadastral);
CREATE INDEX IF NOT EXISTS idx_estab_municipio_sit    ON estabelecimentos (municipio, situacao_cadastral);
CREATE INDEX IF NOT EXISTS idx_estab_situacao         ON estabelecimentos (situacao_cadastral);
CREATE INDEX IF NOT EXISTS idx_empresas_porte         ON empresas (porte);
CREATE INDEX IF NOT EXISTS idx_estab_uf               ON estabelecimentos (uf);

-- Keyset pagination
CREATE INDEX IF NOT EXISTS idx_estab_cursor           ON estabelecimentos (cnpj_basico, cnpj_ordem);

-- Full-Text Search (GIN)
CREATE INDEX IF NOT EXISTS idx_estab_fts_fantasia
    ON estabelecimentos USING GIN (to_tsvector('portuguese', coalesce(nome_fantasia, '')));

CREATE INDEX IF NOT EXISTS idx_empresas_fts_razao
    ON empresas USING GIN (to_tsvector('portuguese', razao_social));
