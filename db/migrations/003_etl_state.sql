-- CNPJ Discovery - ETL State Management

CREATE TABLE etl_state (
    arquivo         TEXT         PRIMARY KEY,
    last_modified   TIMESTAMPTZ,
    checksum_etag   TEXT,
    loaded_at       TIMESTAMPTZ,
    status          TEXT         CHECK (status IN ('pending','downloading','loading','done','error')),
    error_message   TEXT,        -- detalhes do erro quando status='error'
    rows_processed  BIGINT       DEFAULT 0
);

-- Índice para queries de status
CREATE INDEX idx_etl_state_status ON etl_state (status);
