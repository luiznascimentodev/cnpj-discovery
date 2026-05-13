-- CNPJ Discovery - Enrichment seed cursor
-- Persiste o último (cnpj_basico, cnpj_ordem, cnpj_dv) varrido pelo scheduler para
-- cada motivo. Garante que reexecutar o seed nunca volta ao início da tabela
-- estabelecimentos: o resume é literal (cursor monotônico) somado à fila persistente
-- em paid_enrichment.enrichment_targets (status + next_run_at + locked_at).

CREATE TABLE IF NOT EXISTS paid_enrichment.enrichment_seed_cursor (
    reason TEXT PRIMARY KEY,
    last_cnpj_basico CHAR(8) NOT NULL DEFAULT '00000000',
    last_cnpj_ordem CHAR(4) NOT NULL DEFAULT '0000',
    last_cnpj_dv CHAR(2) NOT NULL DEFAULT '00',
    rows_seeded BIGINT NOT NULL DEFAULT 0 CHECK (rows_seeded >= 0),
    last_run_at TIMESTAMPTZ,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

GRANT SELECT, INSERT, UPDATE ON paid_enrichment.enrichment_seed_cursor TO enrichment_worker;
