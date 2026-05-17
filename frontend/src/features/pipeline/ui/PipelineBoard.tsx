import { useEffect } from 'react'
import { monitorForElements } from '@atlaskit/pragmatic-drag-and-drop/element/adapter'
import { autoScrollWindowForElements } from '@atlaskit/pragmatic-drag-and-drop-auto-scroll/element'
import { extractClosestEdge } from '@atlaskit/pragmatic-drag-and-drop-hitbox/closest-edge'
import { Button, Input } from '@/shared/ui'
import { Plus } from '@/shared/ui/icons'
import { groupCardsByStage } from '../model/board'
import { isCardDragData, isCardDropData, targetIndexForEdge } from '../model/drag'
import type { CardWithCompany, StageRecord } from '../schemas'
import { PipelineStageColumn } from './PipelineStageColumn'

interface PipelineBoardProps {
  pipelineId: string
  stages: StageRecord[]
  cards: CardWithCompany[]
  loading: boolean
  onOpenCard: (card: CardWithCompany) => void
  onCreateStage: (name: string) => void
  onMoveCard: (cardId: string, stageId: string, position: number) => void
  onReorderStages: (stageIds: string[]) => void
}

export function PipelineBoard({
  stages,
  cards,
  loading,
  onOpenCard,
  onCreateStage,
  onMoveCard,
}: PipelineBoardProps) {
  const columns = groupCardsByStage(stages, cards)

  useEffect(() => {
    return monitorForElements({
      onDrop({ source, location }) {
        const sourceData = source.data
        if (!isCardDragData(sourceData)) return
        const target = location.current.dropTargets.find((dropTarget) => isCardDropData(dropTarget.data))
        if (!target || !isCardDropData(target.data)) return
        const edge = extractClosestEdge(target.data)
        onMoveCard(sourceData.cardId, target.data.stageId, targetIndexForEdge(target.data.index, edge))
      },
    })
  }, [onMoveCard])

  useEffect(() => autoScrollWindowForElements({ getAllowedAxis: () => 'horizontal' }), [])

  if (loading) {
    return <div className="h-96 rounded-md border border-[var(--color-border)] bg-[var(--color-bg-subtle)]" />
  }

  return (
    <div className="flex min-h-0 flex-1 gap-3 overflow-x-auto pb-3">
      {stages.map((stage) => (
        <PipelineStageColumn
          key={stage.id}
          stage={stage}
          cards={columns[stage.id] ?? []}
          onOpenCard={onOpenCard}
        />
      ))}
      <form
        className="w-72 shrink-0 rounded-md border border-dashed border-[var(--color-border-strong)] bg-[var(--color-bg-surface)] p-3"
        onSubmit={(event) => {
          event.preventDefault()
          const data = new FormData(event.currentTarget)
          const name = String(data.get('name') ?? '').trim()
          if (!name) return
          onCreateStage(name)
          event.currentTarget.reset()
        }}
      >
        <Input name="name" size="sm" placeholder="Novo estágio" aria-label="Nome do estágio" />
        <Button className="mt-2 w-full" size="sm" variant="secondary" type="submit">
          <Plus size={14} aria-hidden="true" /> Adicionar estágio
        </Button>
      </form>
    </div>
  )
}
