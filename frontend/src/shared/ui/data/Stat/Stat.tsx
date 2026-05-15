import { cn } from '@/shared/lib'

export interface StatProps {
  label: string
  value: React.ReactNode
  delta?: { value: string; positive?: boolean }
  className?: string
}

export function Stat({ label, value, delta, className }: StatProps) {
  return (
    <div className={cn('flex flex-col gap-1', className)}>
      <span className="text-[var(--text-xs)] uppercase tracking-wide text-[var(--color-fg-muted)]">{label}</span>
      <span className="text-[var(--text-2xl)] font-semibold text-[var(--color-fg-primary)] tabular-nums">{value}</span>
      {delta && (
        <span className={cn('text-[var(--text-xs)] font-medium', delta.positive ? 'text-[var(--color-success)]' : 'text-[var(--color-danger)]')}>
          {delta.value}
        </span>
      )}
    </div>
  )
}
