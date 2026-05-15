import { type ReactNode } from 'react'
import { cn } from '@/shared/lib'

export interface PageHeaderProps {
  title: ReactNode
  description?: ReactNode
  actions?: ReactNode
  breadcrumb?: ReactNode
  className?: string
}

export function PageHeader({ title, description, actions, breadcrumb, className }: PageHeaderProps) {
  return (
    <header className={cn('flex flex-col gap-2 border-b border-[var(--color-border)] pb-4 mb-6', className)}>
      {breadcrumb && <div className="text-[var(--text-xs)] text-[var(--color-fg-muted)]">{breadcrumb}</div>}
      <div className="flex items-start justify-between gap-4">
        <div className="min-w-0">
          <h1 className="text-[var(--text-2xl)] font-semibold text-[var(--color-fg-primary)] leading-tight">
            {title}
          </h1>
          {description && (
            <p className="mt-1 text-[var(--text-sm)] text-[var(--color-fg-muted)]">{description}</p>
          )}
        </div>
        {actions && <div className="flex shrink-0 items-center gap-2">{actions}</div>}
      </div>
    </header>
  )
}
