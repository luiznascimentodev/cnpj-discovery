import { describe, expect, it } from 'vitest'
import { cardLabel, groupCardsByStage, moveCardOptimistically, reorderStagesOptimistically } from './board'
import type { CardWithCompany, StageRecord } from '../schemas'

const stage = (id: string, position = 0): StageRecord => ({
  id,
  pipeline_id: 'pipeline',
  name: id,
  position,
  color: null,
  is_won: false,
  is_lost: false,
  created_at: '',
  updated_at: '',
})

const card = (id: string, stageId: string, position: number, displayName?: string | null): CardWithCompany => ({
  card: {
    id,
    pipeline_id: 'pipeline',
    stage_id: stageId,
    cnpj_basico: id.padEnd(8, '0').slice(0, 8),
    position,
    display_name: displayName ?? null,
    estimated_value_cents: null,
    notes: null,
    created_at: '',
    updated_at: '',
  },
  company: { razao_social: id === 'b' ? 'Empresa B' : null, uf: null },
})

describe('pipeline board model', () => {
  it('groups cards by stage ordered by position', () => {
    const grouped = groupCardsByStage([stage('todo'), stage('done')], [
      card('b', 'todo', 2),
      card('a', 'todo', 1),
    ])

    expect(grouped.todo.map((item) => item.card.id)).toEqual(['a', 'b'])
    expect(grouped.done).toEqual([])
  })

  it('moves a card optimistically between columns', () => {
    const moved = moveCardOptimistically([
      card('a', 'todo', 0),
      card('b', 'done', 0),
    ], 'a', 'done', 1)

    expect(moved.find((item) => item.card.id === 'a')?.card.stage_id).toBe('done')
    expect(moved.filter((item) => item.card.stage_id === 'done').map((item) => item.card.id)).toEqual(['b', 'a'])
  })

  it('reorders stages optimistically', () => {
    const reordered = reorderStagesOptimistically([stage('a', 0), stage('b', 1)], 'b', 'a')

    expect(reordered.map((item) => item.id)).toEqual(['b', 'a'])
    expect(reordered.map((item) => item.position)).toEqual([0, 1])
  })

  it('uses display name before company and cnpj', () => {
    expect(cardLabel(card('a', 'todo', 0, 'Meu Lead'))).toBe('Meu Lead')
    expect(cardLabel(card('b', 'todo', 0))).toBe('Empresa B')
  })
})
