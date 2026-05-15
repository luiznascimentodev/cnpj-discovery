import { ChevronLeft, ChevronRight } from '@/shared/ui/icons'
import { IconButton } from '../../primitives/IconButton/IconButton'

export interface PaginationProps {
  hasPrev: boolean
  hasNext: boolean
  onPrev: () => void
  onNext: () => void
  pageSize: number
  onPageSizeChange?: (n: number) => void
  pageSizeOptions?: number[]
  totalLabel?: string
}

export function Pagination({
  hasPrev,
  hasNext,
  onPrev,
  onNext,
  pageSize,
  onPageSizeChange,
  pageSizeOptions = [25, 50, 100, 200],
  totalLabel,
}: PaginationProps) {
  return (
    <div className="flex items-center justify-between gap-4 py-3 border-t border-[var(--color-border)]">
      <div className="text-[var(--text-xs)] text-[var(--color-fg-muted)]">{totalLabel}</div>
      <div className="flex items-center gap-3">
        {onPageSizeChange && (
          <label className="flex items-center gap-2 text-[var(--text-xs)] text-[var(--color-fg-secondary)]">
            por página
            <select
              value={pageSize}
              onChange={(e) => onPageSizeChange(Number(e.target.value))}
              className="rounded border border-[var(--color-border-strong)] bg-[var(--color-bg-surface)] px-2 py-1 text-[var(--text-sm)]"
            >
              {pageSizeOptions.map((n) => (
                <option key={n} value={n}>{n}</option>
              ))}
            </select>
          </label>
        )}
        <IconButton variant="secondary" size="sm" aria-label="Página anterior" disabled={!hasPrev} onClick={onPrev}>
          <ChevronLeft size={16} aria-hidden="true" />
        </IconButton>
        <IconButton variant="secondary" size="sm" aria-label="Próxima página" disabled={!hasNext} onClick={onNext}>
          <ChevronRight size={16} aria-hidden="true" />
        </IconButton>
      </div>
    </div>
  )
}
