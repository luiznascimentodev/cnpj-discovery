import { cva, type VariantProps } from 'class-variance-authority'
import { type HTMLAttributes, type ReactNode, forwardRef } from 'react'
import { CircleCheck, CircleX, Info, TriangleAlert, X } from '@/shared/ui/icons'
import { cn } from '@/shared/lib'

const bannerVariants = cva(
  'flex w-full items-center gap-3 border-b px-4 py-2 text-[var(--text-sm)]',
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

export interface BannerProps
  extends HTMLAttributes<HTMLDivElement>,
    VariantProps<typeof bannerVariants> {
  action?: ReactNode
  onDismiss?: () => void
}

export const Banner = forwardRef<HTMLDivElement, BannerProps>(function Banner(
  { className, tone = 'info', action, onDismiss, children, ...rest },
  ref
) {
  const Icon = iconMap[tone ?? 'info']
  return (
    <div ref={ref} role="status" className={cn(bannerVariants({ tone }), className)} {...rest}>
      <Icon aria-hidden="true" className="h-4 w-4 shrink-0" />
      <div className="flex-1">{children}</div>
      {action}
      {onDismiss && (
        <button
          type="button"
          aria-label="Fechar"
          onClick={onDismiss}
          className="rounded p-1 hover:bg-black/5 focus:outline-none focus:ring-2 focus:ring-[var(--color-focus-ring)]"
        >
          <X aria-hidden="true" className="h-4 w-4" />
        </button>
      )}
    </div>
  )
})
