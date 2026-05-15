import { forwardRef } from 'react'
import { cva, type VariantProps } from 'class-variance-authority'
import { cn } from '@/shared/lib'

const inputVariants = cva(
  'flex w-full rounded-md border bg-[var(--color-bg-surface)] text-[var(--color-fg-primary)] ' +
  'placeholder:text-[var(--color-fg-muted)] ' +
  'focus-visible:outline-none focus-visible:shadow-[var(--shadow-focus)] ' +
  'disabled:opacity-50 disabled:cursor-not-allowed transition-shadow',
  {
    variants: {
      size: {
        sm: 'h-8 px-2.5 text-[var(--text-sm)]',
        md: 'h-10 px-3 text-[var(--text-base)]',
      },
      invalid: {
        true:  'border-[var(--color-danger)]',
        false: 'border-[var(--color-border-strong)]',
      },
    },
    defaultVariants: { size: 'md', invalid: false },
  }
)

export interface InputProps
  extends Omit<React.InputHTMLAttributes<HTMLInputElement>, 'size'>,
    VariantProps<typeof inputVariants> {}

export const Input = forwardRef<HTMLInputElement, InputProps>(
  ({ className, size, invalid, ...props }, ref) => (
    <input
      ref={ref}
      aria-invalid={invalid || undefined}
      className={cn(inputVariants({ size, invalid }), className)}
      {...props}
    />
  )
)
Input.displayName = 'Input'
