import { memo, useEffect, useRef, useState } from 'react'
import { draggable, dropTargetForElements } from '@atlaskit/pragmatic-drag-and-drop/element/adapter'
import { combine } from '@atlaskit/pragmatic-drag-and-drop/combine'
import { attachClosestEdge, extractClosestEdge } from '@atlaskit/pragmatic-drag-and-drop-hitbox/closest-edge'
import { cn, formatCurrency } from '@/shared/lib'
import { Badge } from '@/shared/ui'
import { GripVertical } from '@/shared/ui/icons'
import { cardLabel } from '../model/board'
import type { CardWithCompany } from '../schemas'

interface PipelineCardProps {
  item: CardWithCompany
  index: number
  onOpen: (card: CardWithCompany) => void
}

export const PipelineCard = memo(function PipelineCard({ item, index, onOpen }: PipelineCardProps) {
  const ref = useRef<HTMLButtonElement | null>(null)
  const handleRef = useRef<HTMLSpanElement | null>(null)
  const [dragging, setDragging] = useState(false)
  const [edge, setEdge] = useState<string | null>(null)

  useEffect(() => {
    const element = ref.current
    const dragHandle = handleRef.current
    if (!element || !dragHandle) return
    return combine(
      draggable({
        element,
        dragHandle,
        getInitialData: () => ({
          type: 'pipeline-card',
          cardId: item.card.id,
          sourceStageId: item.card.stage_id,
        }),
        onDragStart: () => setDragging(true),
        onDrop: () => setDragging(false),
      }),
      dropTargetForElements({
        element,
        getData: ({ input }) => attachClosestEdge(
          {
            type: 'pipeline-card-drop-target',
            stageId: item.card.stage_id,
            cardId: item.card.id,
            index,
          },
          { element, input, allowedEdges: ['top', 'bottom'] },
        ),
        onDrag: ({ self }) => setEdge(extractClosestEdge(self.data)),
        onDragLeave: () => setEdge(null),
        onDrop: () => setEdge(null),
      }),
    )
  }, [index, item.card.id, item.card.stage_id])

  return (
    <button
      ref={ref}
      type="button"
      className={cn(
        'relative block w-full rounded-md border border-[var(--color-border)] bg-[var(--color-bg-surface)] p-3 text-left shadow-[var(--shadow-sm)]',
        'focus-visible:outline-none focus-visible:shadow-[var(--shadow-focus)] hover:border-[var(--color-border-strong)]',
        dragging && 'opacity-60',
      )}
      onClick={() => onOpen(item)}
      onKeyDown={(event) => {
        if (event.key === 'Enter') onOpen(item)
      }}
    >
      {edge === 'top' && <span className="absolute -top-1 left-2 right-2 h-0.5 rounded bg-[var(--color-action)]" />}
      {edge === 'bottom' && <span className="absolute -bottom-1 left-2 right-2 h-0.5 rounded bg-[var(--color-action)]" />}
      <span className="flex items-start gap-2">
        <span
          ref={handleRef}
          aria-label={`Arrastar card ${cardLabel(item)}`}
          className="mt-0.5 cursor-grab rounded p-1 text-[var(--color-fg-muted)] hover:bg-[var(--color-bg-subtle)]"
        >
          <GripVertical size={16} aria-hidden="true" />
        </span>
        <span className="min-w-0 flex-1">
          <span className="line-clamp-2 text-[var(--text-sm)] font-semibold leading-snug">{cardLabel(item)}</span>
          <span className="mt-1 block text-[var(--text-xs)] text-[var(--color-fg-secondary)]">
            {item.card.cnpj_basico}{item.company.uf ? ` · ${item.company.uf}` : ''}
          </span>
        </span>
      </span>
      <span className="mt-3 flex items-center justify-between gap-2">
        <Badge variant="neutral">{item.company.razao_social ? 'empresa' : 'manual'}</Badge>
        {item.card.estimated_value_cents !== null && (
          <span className="text-[var(--text-xs)] font-medium">
            {formatCurrency(item.card.estimated_value_cents)}
          </span>
        )}
      </span>
    </button>
  )
})
