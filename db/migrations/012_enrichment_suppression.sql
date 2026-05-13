-- CNPJ Discovery - Enrichment suppression workflow
-- Permite remover/marcar contatos como `suppressed` (ex.: pedidos de remoção
-- ou bounces persistentes). O publisher checa esta tabela antes de
-- republicar contatos.

CREATE TABLE IF NOT EXISTS paid_enrichment.suppression_requests (
    id BIGSERIAL PRIMARY KEY,
    cnpj_basico CHAR(8) NOT NULL,
    cnpj_ordem CHAR(4) NOT NULL,
    cnpj_dv CHAR(2) NOT NULL,
    contact_type TEXT NOT NULL CHECK (contact_type IN ('email','phone','whatsapp','website','social')),
    normalized_value TEXT NOT NULL,
    reason TEXT NOT NULL,
    requested_by TEXT NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (cnpj_basico, cnpj_ordem, cnpj_dv, contact_type, normalized_value)
);

CREATE INDEX IF NOT EXISTS idx_suppression_lookup
    ON paid_enrichment.suppression_requests (contact_type, normalized_value);

GRANT SELECT, INSERT ON paid_enrichment.suppression_requests TO enrichment_worker, api_paid;
GRANT USAGE, SELECT ON ALL SEQUENCES IN SCHEMA paid_enrichment TO enrichment_worker, api_paid;
