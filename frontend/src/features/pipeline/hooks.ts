import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { pipelineApi } from './api'

export const pipelineKeys = {
  root: ['pipeline'] as const,
  pipelines: () => [...pipelineKeys.root, 'pipelines'] as const,
  stages: (pipelineId: string | null) => [...pipelineKeys.root, pipelineId, 'stages'] as const,
  cards: (pipelineId: string | null) => [...pipelineKeys.root, pipelineId, 'cards'] as const,
  imports: (pipelineId: string, cardId: string) => [...pipelineKeys.root, pipelineId, 'cards', cardId, 'imports'] as const,
  activities: (pipelineId: string, cardId: string) => [...pipelineKeys.root, pipelineId, 'cards', cardId, 'activities'] as const,
  tasks: (pipelineId: string, cardId: string) => [...pipelineKeys.root, pipelineId, 'cards', cardId, 'tasks'] as const,
}

export function usePipelines() {
  return useQuery({ queryKey: pipelineKeys.pipelines(), queryFn: pipelineApi.listPipelines })
}

export function usePipelineData(pipelineId: string | null) {
  const stages = useQuery({
    queryKey: pipelineKeys.stages(pipelineId),
    queryFn: () => pipelineApi.listStages(pipelineId as string),
    enabled: Boolean(pipelineId),
  })
  const cards = useQuery({
    queryKey: pipelineKeys.cards(pipelineId),
    queryFn: () => pipelineApi.listCards(pipelineId as string),
    enabled: Boolean(pipelineId),
  })
  return { stages, cards }
}

export function usePipelineMutations(pipelineId: string | null) {
  const queryClient = useQueryClient()
  const invalidateBoard = () => {
    if (!pipelineId) return
    void queryClient.invalidateQueries({ queryKey: pipelineKeys.stages(pipelineId) })
    void queryClient.invalidateQueries({ queryKey: pipelineKeys.cards(pipelineId) })
  }

  return {
    createPipeline: useMutation({
      mutationFn: pipelineApi.createPipeline,
      onSuccess: () => void queryClient.invalidateQueries({ queryKey: pipelineKeys.pipelines() }),
    }),
    createStage: useMutation({
      mutationFn: (payload: { name: string; color?: string | null }) => pipelineApi.createStage(pipelineId as string, payload),
      onSuccess: invalidateBoard,
    }),
    reorderStages: useMutation({
      mutationFn: (stageIds: string[]) => pipelineApi.reorderStages(pipelineId as string, stageIds),
      onSuccess: invalidateBoard,
    }),
    createCard: useMutation({
      mutationFn: (payload: { cnpj_basico: string; stage_id?: string | null; display_name?: string | null; notes?: string | null }) =>
        pipelineApi.createCard(pipelineId as string, payload),
      onSuccess: invalidateBoard,
    }),
    updateCard: useMutation({
      mutationFn: ({ cardId, payload }: { cardId: string; payload: { display_name?: string | null; estimated_value_cents?: number | null; notes?: string | null } }) =>
        pipelineApi.updateCard(pipelineId as string, cardId, payload),
      onSuccess: invalidateBoard,
    }),
    moveCard: useMutation({
      mutationFn: ({ cardId, stageId, position }: { cardId: string; stageId: string; position: number }) =>
        pipelineApi.moveCard(pipelineId as string, cardId, { stage_id: stageId, position }),
      onSuccess: invalidateBoard,
    }),
    deleteCard: useMutation({
      mutationFn: (cardId: string) => pipelineApi.deleteCard(pipelineId as string, cardId),
      onSuccess: invalidateBoard,
    }),
    importCards: useMutation({
      mutationFn: (payload: { stageId: string; file: File }) => pipelineApi.importCards(pipelineId as string, payload),
      onSuccess: invalidateBoard,
    }),
  }
}

export function useCardDetail(pipelineId: string | null, cardId: string | null) {
  const enabled = Boolean(pipelineId && cardId)
  return {
    importRows: useQuery({
      queryKey: pipelineId && cardId ? pipelineKeys.imports(pipelineId, cardId) : pipelineKeys.root,
      queryFn: () => pipelineApi.listCardImportRows(pipelineId as string, cardId as string),
      enabled,
    }),
    activities: useQuery({
      queryKey: pipelineId && cardId ? pipelineKeys.activities(pipelineId, cardId) : pipelineKeys.root,
      queryFn: () => pipelineApi.listActivities(pipelineId as string, cardId as string),
      enabled,
    }),
    tasks: useQuery({
      queryKey: pipelineId && cardId ? pipelineKeys.tasks(pipelineId, cardId) : pipelineKeys.root,
      queryFn: () => pipelineApi.listTasks(pipelineId as string, cardId as string),
      enabled,
    }),
  }
}

export function useCardDetailMutations(pipelineId: string, cardId: string) {
  const queryClient = useQueryClient()
  return {
    createActivity: useMutation({
      mutationFn: pipelineApi.createActivity.bind(null, pipelineId, cardId),
      onSuccess: () => void queryClient.invalidateQueries({ queryKey: pipelineKeys.activities(pipelineId, cardId) }),
    }),
    createTask: useMutation({
      mutationFn: pipelineApi.createTask.bind(null, pipelineId, cardId),
      onSuccess: () => void queryClient.invalidateQueries({ queryKey: pipelineKeys.tasks(pipelineId, cardId) }),
    }),
    updateTask: useMutation({
      mutationFn: ({ taskId, done_at }: { taskId: string; done_at: string | null }) =>
        pipelineApi.updateTask(pipelineId, cardId, taskId, { done_at }),
      onSuccess: () => void queryClient.invalidateQueries({ queryKey: pipelineKeys.tasks(pipelineId, cardId) }),
    }),
  }
}

