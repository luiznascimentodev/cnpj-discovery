import { memo, useEffect, useRef } from 'react'
import { dropTargetForElements } from '@atlaskit/pragmatic-drag-and-drop/element/adapter'
import { autoScrollForElements } from '@atlaskit/pragmatic-drag-and-drop-auto-scroll/element'
import { useVirtualizer } from '@tanstack/react-virtual'
import { Badge } from '@/shared/ui'
import type { CardWithCompany, StageRecord } from '../schemas'
import { PipelineCard } from './PipelineCard'

interface PipelineStageColumnProps {
  stage: StageRecord
  cards: CardWithCompany[]
  onOpenCard: (card: CardWithCompany) => void
}

export const PipelineStageColumn = memo(function PipelineStageColumn({
  stage,
  cards,
  onOpenCard,
}: PipelineStageColumnProps) {
  const columnRef = useRef<HTMLDivElement | null>(null)
  const scrollRef = useRef<HTMLDivElement | null>(null)
  const shouldVirtualize = cards.length > 80
  const virtualizer = useVirtualizer({
    count: cards.length,
    getScrollElement: () => scrollRef.current,
    estimateSize: () => 118,
    overscan: 8,
    enabled: shouldVirtualize,
  })
  const visibleItems = shouldVirtualize ? virtualizer.getVirtualItems() : []

  useEffect(() => {
    const element = columnRef.current
    if (!element) return
    return dropTargetForElements({
      element,
      getData: () => ({ type: 'pipeline-card-drop-target', stageId: stage.id, index: cards.length }),
    })
  }, [cards.length, stage.id])

  useEffect(() => {
    const element = scrollRef.current
    if (!element) return
    return autoScrollForElements({ element, getAllowedAxis: () => 'vertical' })
  }, [])

  return (
    <section
      ref={columnRef}
      className="flex h-[calc(100vh-260px)] min-h-[520px] w-80 shrink-0 flex-col rounded-md border border-[var(--color-border)] bg-[var(--color-bg-surface)]"
    >
      <header className="flex items-center justify-between border-b border-[var(--color-border)] px-3 py-2">
        <div className="min-w-0">
          <h2 className="truncate text-[var(--text-sm)] font-semibold">{stage.name}</h2>
          <p className="text-[var(--text-xs)] text-[var(--color-fg-secondary)]">posição {stage.position + 1}</p>
        </div>
        <Badge variant={stage.is_won ? 'success' : stage.is_lost ? 'danger' : 'neutral'}>{cards.length}</Badge>
      </header>
      <div ref={scrollRef} className="min-h-0 flex-1 overflow-y-auto p-2">
        {shouldVirtualize ? (
          <div style={{ height: virtualizer.getTotalSize(), position: 'relative' }}>
            {visibleItems.map((virtualItem) => {
              const item = cards[virtualItem.index]
              return (
                <div
                  key={item.card.id}
                  style={{
                    position: 'absolute',
                    top: 0,
                    left: 0,
                    width: '100%',
                    transform: `translateY(${virtualItem.start}px)`,
                  }}
                >
                  <PipelineCard item={item} index={virtualItem.index} onOpen={onOpenCard} />
                </div>
              )
            })}
          </div>
        ) : (
          <div className="space-y-2">
            {cards.map((item, index) => (
              <PipelineCard key={item.card.id} item={item} index={index} onOpen={onOpenCard} />
            ))}
          </div>
        )}
      </div>
    </section>
  )
})
