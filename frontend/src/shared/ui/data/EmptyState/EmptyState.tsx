import { cn } from '@/shared/lib'
import type { ComponentType, SVGProps } from 'react'
type LucideIcon = ComponentType<SVGProps<SVGSVGElement> & { size?: number | string }>

export interface EmptyStateProps {
  icon: LucideIcon
  title: string
  description?: string
  action?: React.ReactNode
  className?: string
}

export function EmptyState({ icon: Icon, title, description, action, className }: EmptyStateProps) {
  return (
    <div className={cn('flex flex-col items-center justify-center text-center py-12 px-6', className)}>
      <Icon size={40} className="text-[var(--color-fg-muted)]" aria-hidden="true" />
      <h3 className="mt-4 text-[var(--text-md)] font-semibold text-[var(--color-fg-primary)]">{title}</h3>
      {description && (
        <p className="mt-1 text-[var(--text-sm)] text-[var(--color-fg-secondary)] max-w-md">{description}</p>
      )}
      {action && <div className="mt-4">{action}</div>}
    </div>
  )
}
