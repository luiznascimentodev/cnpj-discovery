import { api } from '@/shared/api'
import type {
  ActivityKind,
  ActivityRecord,
  CardRecord,
  CardWithCompany,
  ImportResult,
  ImportRowRecord,
  PipelineRecord,
  StageRecord,
  TaskRecord,
} from './schemas'

export const pipelineApi = {
  listPipelines: () =>
    api.get<PipelineRecord[]>('/pipelines').then((response) => response.data),

  createPipeline: (payload: { name: string; description?: string | null }) =>
    api.post<PipelineRecord>('/pipelines', payload).then((response) => response.data),

  listStages: (pipelineId: string) =>
    api.get<StageRecord[]>(`/pipelines/${pipelineId}/stages`).then((response) => response.data),

  createStage: (pipelineId: string, payload: { name: string; color?: string | null }) =>
    api.post<StageRecord>(`/pipelines/${pipelineId}/stages`, payload).then((response) => response.data),

  updateStage: (pipelineId: string, stageId: string, payload: { name?: string; color?: string | null }) =>
    api.patch<StageRecord>(`/pipelines/${pipelineId}/stages/${stageId}`, payload).then((response) => response.data),

  reorderStages: (pipelineId: string, stageIds: string[]) =>
    api.post<void>(`/pipelines/${pipelineId}/stages/reorder`, { stage_ids: stageIds }).then(() => undefined),

  deleteStage: (pipelineId: string, stageId: string, moveCardsTo?: string) =>
    api.delete<void>(`/pipelines/${pipelineId}/stages/${stageId}`, {
      params: moveCardsTo ? { move_cards_to: moveCardsTo } : undefined,
    }).then(() => undefined),

  listCards: (pipelineId: string) =>
    api.get<CardWithCompany[]>(`/pipelines/${pipelineId}/cards`).then((response) => response.data),

  createCard: (pipelineId: string, payload: {
    cnpj_basico: string
    stage_id?: string | null
    display_name?: string | null
    estimated_value_cents?: number | null
    notes?: string | null
  }) =>
    api.post<CardRecord>(`/pipelines/${pipelineId}/cards`, payload).then((response) => response.data),

  updateCard: (pipelineId: string, cardId: string, payload: {
    display_name?: string | null
    estimated_value_cents?: number | null
    notes?: string | null
  }) =>
    api.patch<CardRecord>(`/pipelines/${pipelineId}/cards/${cardId}`, payload).then((response) => response.data),

  moveCard: (pipelineId: string, cardId: string, payload: { stage_id: string; position: number }) =>
    api.post<CardRecord>(`/pipelines/${pipelineId}/cards/${cardId}/move`, payload).then((response) => response.data),

  deleteCard: (pipelineId: string, cardId: string) =>
    api.delete<void>(`/pipelines/${pipelineId}/cards/${cardId}`).then(() => undefined),

  importCards: (pipelineId: string, payload: { stageId: string; file: File }) => {
    const form = new FormData()
    form.set('stage_id', payload.stageId)
    form.set('file', payload.file)
    return api.post<ImportResult>(`/pipelines/${pipelineId}/cards/import`, form).then((response) => response.data)
  },

  listCardImportRows: (pipelineId: string, cardId: string) =>
    api.get<ImportRowRecord[]>(`/pipelines/${pipelineId}/cards/${cardId}/import-metadata`).then((response) => response.data),

  listActivities: (pipelineId: string, cardId: string) =>
    api.get<ActivityRecord[]>(`/pipelines/${pipelineId}/cards/${cardId}/activities`).then((response) => response.data),

  createActivity: (pipelineId: string, cardId: string, payload: { kind: ActivityKind; body: string }) =>
    api.post<ActivityRecord>(`/pipelines/${pipelineId}/cards/${cardId}/activities`, payload).then((response) => response.data),

  listTasks: (pipelineId: string, cardId: string) =>
    api.get<TaskRecord[]>(`/pipelines/${pipelineId}/cards/${cardId}/tasks`).then((response) => response.data),

  createTask: (pipelineId: string, cardId: string, payload: { title: string; due_at?: string | null }) =>
    api.post<TaskRecord>(`/pipelines/${pipelineId}/cards/${cardId}/tasks`, payload).then((response) => response.data),

  updateTask: (pipelineId: string, cardId: string, taskId: string, payload: { title?: string; due_at?: string | null; done_at?: string | null }) =>
    api.patch<TaskRecord>(`/pipelines/${pipelineId}/cards/${cardId}/tasks/${taskId}`, payload).then((response) => response.data),
}
