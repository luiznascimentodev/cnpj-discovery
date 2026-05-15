import { Slot } from '@radix-ui/react-slot'
import { cva, type VariantProps } from 'class-variance-authority'
import { forwardRef } from 'react'
import { Loader2 } from '@/shared/ui/icons'
import { cn } from '@/shared/lib'

const buttonVariants = cva(
  'inline-flex items-center justify-center gap-2 whitespace-nowrap rounded-md font-medium ' +
  'transition-colors transition-shadow ' +
  'focus-visible:outline-none focus-visible:shadow-[var(--shadow-focus)] ' +
  'disabled:pointer-events-none disabled:opacity-50',
  {
    variants: {
      variant: {
        primary:   'bg-[var(--color-action)] text-[var(--color-action-fg)] hover:bg-[var(--color-action-hover)]',
        secondary: 'bg-[var(--color-bg-surface)] text-[var(--color-fg-primary)] border border-[var(--color-border-strong)] hover:bg-[var(--color-bg-subtle)]',
        ghost:     'bg-transparent text-[var(--color-fg-primary)] hover:bg-[var(--color-bg-subtle)]',
        danger:    'bg-[var(--color-danger)] text-white hover:opacity-90',
        link:      'bg-transparent text-[var(--color-action)] underline-offset-2 hover:underline p-0 h-auto',
      },
      size: {
        sm: 'h-8 px-3 text-[var(--text-sm)]',
        md: 'h-10 px-4 text-[var(--text-base)]',
        lg: 'h-12 px-6 text-[var(--text-md)]',
      },
    },
    defaultVariants: { variant: 'primary', size: 'md' },
  }
)

export interface ButtonProps
  extends React.ButtonHTMLAttributes<HTMLButtonElement>,
    VariantProps<typeof buttonVariants> {
  asChild?: boolean
  loading?: boolean
}

export const Button = forwardRef<HTMLButtonElement, ButtonProps>(
  ({ className, variant, size, asChild = false, loading = false, disabled, children, ...props }, ref) => {
    const Comp = asChild ? Slot : 'button'
    return (
      <Comp
        ref={ref}
        className={cn(buttonVariants({ variant, size }), className)}
        disabled={disabled ?? loading}
        aria-busy={loading || undefined}
        {...props}
      >
        {loading && <Loader2 className="animate-spin" size={16} aria-hidden="true" />}
        {children}
      </Comp>
    )
  }
)
Button.displayName = 'Button'

export { buttonVariants }
