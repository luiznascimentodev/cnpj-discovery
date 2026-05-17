import type { Edge } from '@atlaskit/pragmatic-drag-and-drop-hitbox/closest-edge'

export type CardDragData = {
  type: 'pipeline-card'
  cardId: string
  sourceStageId: string
}

export type CardDropData = {
  type: 'pipeline-card-drop-target'
  stageId: string
  cardId?: string
  index: number
}

export type StageDragData = {
  type: 'pipeline-stage'
  stageId: string
}

export type StageDropData = {
  type: 'pipeline-stage-drop-target'
  stageId: string
}

export const isCardDragData = (value: Record<string, unknown>): value is CardDragData =>
  value.type === 'pipeline-card' && typeof value.cardId === 'string'

export const isCardDropData = (value: Record<string, unknown>): value is CardDropData =>
  value.type === 'pipeline-card-drop-target' && typeof value.stageId === 'string'

export const targetIndexForEdge = (index: number, edge: Edge | null): number =>
  edge === 'bottom' ? index + 1 : index
