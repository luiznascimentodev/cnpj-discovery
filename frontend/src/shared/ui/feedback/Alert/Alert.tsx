import { cva, type VariantProps } from 'class-variance-authority'
import { type HTMLAttributes, type ReactNode, forwardRef } from 'react'
import { CircleCheck, CircleX, Info, TriangleAlert } from '@/shared/ui/icons'
import { cn } from '@/shared/lib'

const alertVariants = cva(
  'flex gap-3 rounded-lg border p-3 text-[var(--text-sm)]',
  {
    variants: {
      tone: {
        info: 'border-[var(--color-info-border)] bg-[var(--color-info-bg)] text-[var(--color-info-fg)]',
        success:
          'border-[var(--color-success-border)] bg-[var(--color-success-bg)] text-[var(--color-success-fg)]',
        warning:
          'border-[var(--color-warning-border)] bg-[var(--color-warning-bg)] text-[var(--color-warning-fg)]',
        danger:
          'border-[var(--color-danger-border)] bg-[var(--color-danger-bg)] text-[var(--color-danger-fg)]',
      },
    },
    defaultVariants: { tone: 'info' },
  }
)

const iconMap = { info: Info, success: CircleCheck, warning: TriangleAlert, danger: CircleX }

export interface AlertProps
  extends Omit<HTMLAttributes<HTMLDivElement>, 'title'>,
    VariantProps<typeof alertVariants> {
  title?: ReactNode
}

export const Alert = forwardRef<HTMLDivElement, AlertProps>(function Alert(
  { className, tone = 'info', title, children, ...rest },
  ref
) {
  const Icon = iconMap[tone ?? 'info']
  return (
    <div ref={ref} role="alert" className={cn(alertVariants({ tone }), className)} {...rest}>
      <Icon aria-hidden="true" className="mt-0.5 h-4 w-4 shrink-0" />
      <div className="flex-1">
        {title && <div className="font-semibold mb-0.5">{title}</div>}
        {children && <div className="text-[var(--text-sm)] opacity-90">{children}</div>}
      </div>
    </div>
  )
})
