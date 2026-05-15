import { cva, type VariantProps } from 'class-variance-authority'
import { cn } from '@/shared/lib'

const badgeVariants = cva(
  'inline-flex items-center gap-1 rounded-full px-2 py-0.5 text-[var(--text-xs)] font-medium border',
  {
    variants: {
      variant: {
        neutral: 'bg-[var(--color-gray-100)] text-[var(--color-gray-700)] border-[var(--color-gray-200)]',
        info:    'bg-[var(--color-info-bg)] text-[var(--color-info)] border-[var(--color-blue-100)]',
        success: 'bg-[var(--color-success-bg)] text-[var(--color-success)] border-[var(--color-green-100)]',
        warning: 'bg-[var(--color-warning-bg)] text-[var(--color-warning)] border-[var(--color-amber-100)]',
        danger:  'bg-[var(--color-danger-bg)] text-[var(--color-danger)] border-[var(--color-red-100)]',
        brand:   'bg-[var(--color-yellow-100)] text-[var(--color-amber-600)] border-[var(--color-yellow-400)]',
      },
    },
    defaultVariants: { variant: 'neutral' },
  }
)

export interface BadgeProps
  extends React.HTMLAttributes<HTMLSpanElement>,
    VariantProps<typeof badgeVariants> {}

export function Badge({ className, variant, ...props }: BadgeProps) {
  return <span className={cn(badgeVariants({ variant }), className)} {...props} />
}

export { badgeVariants }
