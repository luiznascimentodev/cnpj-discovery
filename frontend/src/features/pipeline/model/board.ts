import type { CardWithCompany, StageRecord } from '../schemas'

export type BoardColumns = Record<string, CardWithCompany[]>

export const cardLabel = (item: CardWithCompany): string =>
  item.card.display_name?.trim() || item.company.razao_social?.trim() || item.card.cnpj_basico

export const groupCardsByStage = (
  stages: StageRecord[],
  cards: CardWithCompany[],
): BoardColumns => {
  const grouped = Object.fromEntries(stages.map((stage) => [stage.id, [] as CardWithCompany[]]))
  for (const item of cards) {
    if (!grouped[item.card.stage_id]) grouped[item.card.stage_id] = []
    grouped[item.card.stage_id].push(item)
  }
  for (const stageId of Object.keys(grouped)) {
    grouped[stageId].sort((a, b) => a.card.position - b.card.position)
  }
  return grouped
}

export const moveCardOptimistically = (
  cards: CardWithCompany[],
  cardId: string,
  targetStageId: string,
  targetIndex: number,
): CardWithCompany[] => {
  const moving = cards.find((item) => item.card.id === cardId)
  if (!moving) return cards

  const withoutMoving = cards.filter((item) => item.card.id !== cardId)
  const columns = groupCardsByStage(
    Array.from(new Set(cards.map((item) => item.card.stage_id))).map((id, position) => ({
      id,
      pipeline_id: moving.card.pipeline_id,
      name: id,
      position,
      color: null,
      is_won: false,
      is_lost: false,
      created_at: '',
      updated_at: '',
    })),
    withoutMoving,
  )
  const target = columns[targetStageId] ?? []
  const nextIndex = Math.max(0, Math.min(targetIndex, target.length))
  target.splice(nextIndex, 0, { ...moving, card: { ...moving.card, stage_id: targetStageId, position: nextIndex } })

  return Object.values(columns).flatMap((items) =>
    items.map((item, position) => ({
      ...item,
      card: { ...item.card, position },
    })),
  )
}

export const reorderStagesOptimistically = (
  stages: StageRecord[],
  sourceId: string,
  targetId: string,
): StageRecord[] => {
  const sourceIndex = stages.findIndex((stage) => stage.id === sourceId)
  const targetIndex = stages.findIndex((stage) => stage.id === targetId)
  if (sourceIndex < 0 || targetIndex < 0 || sourceIndex === targetIndex) return stages
  const next = [...stages]
  const [stage] = next.splice(sourceIndex, 1)
  next.splice(targetIndex, 0, stage)
  return next.map((item, position) => ({ ...item, position }))
}
