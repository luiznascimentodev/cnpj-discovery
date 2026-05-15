import { forwardRef } from 'react'
import { cn } from '@/shared/lib'

export interface TextareaProps extends React.TextareaHTMLAttributes<HTMLTextAreaElement> {
  invalid?: boolean
}

export const Textarea = forwardRef<HTMLTextAreaElement, TextareaProps>(
  ({ className, invalid, ...props }, ref) => (
    <textarea
      ref={ref}
      aria-invalid={invalid || undefined}
      className={cn(
        'flex w-full rounded-md border bg-[var(--color-bg-surface)] px-3 py-2 text-[var(--text-base)]',
        'placeholder:text-[var(--color-fg-muted)] focus-visible:outline-none focus-visible:shadow-[var(--shadow-focus)]',
        invalid ? 'border-[var(--color-danger)]' : 'border-[var(--color-border-strong)]',
        className
      )}
      {...props}
    />
  )
)
Textarea.displayName = 'Textarea'
