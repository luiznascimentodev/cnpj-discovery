import * as LabelPrimitive from '@radix-ui/react-label'
import { forwardRef } from 'react'
import { cn } from '@/shared/lib'

export interface LabelProps extends React.ComponentPropsWithoutRef<typeof LabelPrimitive.Root> {
  required?: boolean
}

export const Label = forwardRef<React.ElementRef<typeof LabelPrimitive.Root>, LabelProps>(
  ({ className, children, required, ...props }, ref) => (
    <LabelPrimitive.Root
      ref={ref}
      className={cn('text-[var(--text-sm)] font-medium text-[var(--color-fg-primary)]', className)}
      {...props}
    >
      {children}
      {required && <span aria-hidden="true" className="text-[var(--color-danger)] ml-0.5">*</span>}
    </LabelPrimitive.Root>
  )
)
Label.displayName = 'Label'
