export interface PipelineRecord {
  id: string
  owner_user_id: string
  name: string
  description: string | null
  archived_at: string | null
  created_at: string
  updated_at: string
}

export interface StageRecord {
  id: string
  pipeline_id: string
  name: string
  position: number
  color: string | null
  is_won: boolean
  is_lost: boolean
  created_at: string
  updated_at: string
}

export interface CardRecord {
  id: string
  pipeline_id: string
  stage_id: string
  cnpj_basico: string
  position: number
  display_name: string | null
  estimated_value_cents: number | null
  notes: string | null
  created_at: string
  updated_at: string
}

export interface CompanySummary {
  razao_social: string | null
  uf: string | null
}

export interface CardWithCompany {
  card: CardRecord
  company: CompanySummary
}

export interface ImportBatchRecord {
  id: string
  pipeline_id: string
  owner_user_id: string
  stage_id: string
  filename: string | null
  file_size_bytes: number
  content_sha256: string
  total_rows: number
  created_count: number
  skipped_count: number
  created_at: string
}

export type ImportSkipReason = 'invalid_cnpj_format' | 'cnpj_not_found' | 'duplicate_in_pipeline'

export interface ImportRowRecord {
  id: number
  batch_id: string
  line_number: number
  raw_cnpj: string
  cnpj_basico: string | null
  display_name: string | null
  card_id: string | null
  status: 'created' | 'skipped'
  reason: ImportSkipReason | null
  metadata: Record<string, unknown>
  created_at: string
}

export interface ImportResult {
  batch: ImportBatchRecord
  created: number
  skipped: Array<{ line: number; cnpj: string; reason: ImportSkipReason }>
  summary: {
    total_rows: number
    valid_rows: number
    invalid_rows: number
    duplicates_in_file: number
  }
}

export type ActivityKind = 'note' | 'call' | 'email' | 'meeting'

export interface ActivityRecord {
  id: string
  card_id: string
  author_user_id: string
  kind: ActivityKind
  body: string
  occurred_at: string
  created_at: string
}

export interface TaskRecord {
  id: string
  card_id: string
  assignee_user_id: string
  title: string
  due_at: string | null
  done_at: string | null
  created_at: string
  updated_at: string
}

export interface PipelineBoardData {
  pipelines: PipelineRecord[]
  pipeline: PipelineRecord | null
  stages: StageRecord[]
  cards: CardWithCompany[]
}
