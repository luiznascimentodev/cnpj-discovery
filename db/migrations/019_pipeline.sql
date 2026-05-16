-- ============================================================
-- 019_pipeline.sql
-- Sales pipeline (Kanban): pipelines + stages + cards + activities + tasks + stage history
-- ============================================================

CREATE TABLE pipelines (
  id            UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  owner_user_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  name          TEXT NOT NULL,
  description   TEXT,
  archived_at   TIMESTAMPTZ,
  created_at    TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  updated_at    TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE INDEX pipelines_owner_active ON pipelines (owner_user_id, created_at DESC)
  WHERE archived_at IS NULL;

CREATE TABLE pipeline_stages (
  id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  pipeline_id UUID NOT NULL REFERENCES pipelines(id) ON DELETE CASCADE,
  name        TEXT NOT NULL,
  position    INTEGER NOT NULL,
  color       TEXT,
  is_won      BOOLEAN NOT NULL DEFAULT FALSE,
  is_lost     BOOLEAN NOT NULL DEFAULT FALSE,
  created_at  TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  updated_at  TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  UNIQUE (pipeline_id, position) DEFERRABLE INITIALLY DEFERRED,
  CHECK (NOT (is_won AND is_lost)),
  CHECK (position >= 0)
);
CREATE INDEX pipeline_stages_pipeline ON pipeline_stages (pipeline_id, position);

CREATE TABLE pipeline_cards (
  id                    UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  pipeline_id           UUID NOT NULL REFERENCES pipelines(id) ON DELETE CASCADE,
  stage_id              UUID NOT NULL REFERENCES pipeline_stages(id) ON DELETE RESTRICT,
  cnpj_basico           CHAR(8) NOT NULL,
  position              INTEGER NOT NULL,
  estimated_value_cents BIGINT,
  notes                 TEXT,
  created_at            TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  updated_at            TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  UNIQUE (pipeline_id, cnpj_basico),
  UNIQUE (stage_id, position) DEFERRABLE INITIALLY DEFERRED,
  CHECK (position >= 0),
  CHECK (cnpj_basico ~ '^\d{8}$')
);
CREATE INDEX pipeline_cards_stage ON pipeline_cards (stage_id, position);
CREATE INDEX pipeline_cards_pipeline ON pipeline_cards (pipeline_id);
CREATE INDEX pipeline_cards_cnpj ON pipeline_cards (cnpj_basico);

CREATE TABLE pipeline_card_activities (
  id             UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  card_id        UUID NOT NULL REFERENCES pipeline_cards(id) ON DELETE CASCADE,
  author_user_id UUID NOT NULL REFERENCES users(id) ON DELETE RESTRICT,
  kind           TEXT NOT NULL CHECK (kind IN ('note','call','email','meeting')),
  body           TEXT NOT NULL,
  occurred_at    TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  created_at     TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE INDEX pipeline_card_activities_card
  ON pipeline_card_activities (card_id, occurred_at DESC);

CREATE TABLE pipeline_card_tasks (
  id               UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  card_id          UUID NOT NULL REFERENCES pipeline_cards(id) ON DELETE CASCADE,
  assignee_user_id UUID NOT NULL REFERENCES users(id) ON DELETE RESTRICT,
  title            TEXT NOT NULL,
  due_at           TIMESTAMPTZ,
  done_at          TIMESTAMPTZ,
  created_at       TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  updated_at       TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE INDEX pipeline_card_tasks_open
  ON pipeline_card_tasks (assignee_user_id, due_at) WHERE done_at IS NULL;
CREATE INDEX pipeline_card_tasks_card
  ON pipeline_card_tasks (card_id, created_at DESC);

CREATE TABLE pipeline_card_stage_changes (
  id                 BIGSERIAL PRIMARY KEY,
  card_id            UUID NOT NULL REFERENCES pipeline_cards(id) ON DELETE CASCADE,
  from_stage_id      UUID REFERENCES pipeline_stages(id) ON DELETE SET NULL,
  to_stage_id        UUID NOT NULL REFERENCES pipeline_stages(id) ON DELETE SET NULL,
  changed_by_user_id UUID NOT NULL REFERENCES users(id) ON DELETE RESTRICT,
  changed_at         TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE INDEX pipeline_card_stage_changes_card
  ON pipeline_card_stage_changes (card_id, changed_at DESC);
