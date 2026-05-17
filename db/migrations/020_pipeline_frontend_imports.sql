-- ============================================================
-- 020_pipeline_frontend_imports.sql
-- Pipeline frontend support: card display names + persistent CSV import audit
-- ============================================================

ALTER TABLE pipeline_cards
  ADD COLUMN IF NOT EXISTS display_name TEXT;

CREATE INDEX IF NOT EXISTS pipeline_cards_pipeline_stage_position
  ON pipeline_cards (pipeline_id, stage_id, position);

CREATE INDEX IF NOT EXISTS pipeline_cards_pipeline_updated
  ON pipeline_cards (pipeline_id, updated_at DESC);

CREATE TABLE IF NOT EXISTS pipeline_card_import_batches (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  pipeline_id UUID NOT NULL REFERENCES pipelines(id) ON DELETE CASCADE,
  owner_user_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  stage_id UUID NOT NULL REFERENCES pipeline_stages(id) ON DELETE RESTRICT,
  filename TEXT,
  file_size_bytes BIGINT NOT NULL DEFAULT 0,
  content_sha256 TEXT NOT NULL,
  total_rows INTEGER NOT NULL DEFAULT 0,
  created_count INTEGER NOT NULL DEFAULT 0,
  skipped_count INTEGER NOT NULL DEFAULT 0,
  created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS pipeline_card_import_batches_owner_created
  ON pipeline_card_import_batches (owner_user_id, created_at DESC);

CREATE INDEX IF NOT EXISTS pipeline_card_import_batches_pipeline_created
  ON pipeline_card_import_batches (pipeline_id, created_at DESC);

CREATE INDEX IF NOT EXISTS pipeline_card_import_batches_sha
  ON pipeline_card_import_batches (content_sha256);

CREATE UNIQUE INDEX IF NOT EXISTS pipeline_card_import_batches_latest_file
  ON pipeline_card_import_batches (owner_user_id, pipeline_id, filename, file_size_bytes);

CREATE TABLE IF NOT EXISTS pipeline_card_import_rows (
  id BIGSERIAL PRIMARY KEY,
  batch_id UUID NOT NULL REFERENCES pipeline_card_import_batches(id) ON DELETE CASCADE,
  line_number INTEGER NOT NULL,
  raw_cnpj TEXT NOT NULL,
  cnpj_basico CHAR(8),
  display_name TEXT,
  card_id UUID REFERENCES pipeline_cards(id) ON DELETE SET NULL,
  status TEXT NOT NULL CHECK (status IN ('created','skipped')),
  reason TEXT CHECK (reason IN ('invalid_cnpj_format','cnpj_not_found','duplicate_in_pipeline')),
  metadata JSONB NOT NULL DEFAULT '{}'::jsonb,
  created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS pipeline_card_import_rows_batch_line
  ON pipeline_card_import_rows (batch_id, line_number);

CREATE INDEX IF NOT EXISTS pipeline_card_import_rows_cnpj
  ON pipeline_card_import_rows (cnpj_basico) WHERE cnpj_basico IS NOT NULL;

CREATE INDEX IF NOT EXISTS pipeline_card_import_rows_card
  ON pipeline_card_import_rows (card_id) WHERE card_id IS NOT NULL;

CREATE INDEX IF NOT EXISTS pipeline_card_import_rows_metadata_gin
  ON pipeline_card_import_rows USING GIN (metadata);
