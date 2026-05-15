import { Loader2 } from '@/shared/ui/icons'
import { cn } from '@/shared/lib'

export interface SpinnerProps {
  size?: number
  className?: string
  'aria-label'?: string
}

export function Spinner({ size = 16, className, 'aria-label': ariaLabel = 'Carregando' }: SpinnerProps) {
  return (
    <Loader2
      size={size}
      className={cn('animate-spin text-[var(--color-fg-muted)]', className)}
      role="status"
      aria-label={ariaLabel}
    />
  )
}
