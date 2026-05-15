import * as Checkbox from '@radix-ui/react-checkbox'
import { forwardRef } from 'react'
import { Check } from '@/shared/ui/icons'
import { cn } from '@/shared/lib'

const CheckboxImpl = forwardRef<
  React.ElementRef<typeof Checkbox.Root>,
  React.ComponentPropsWithoutRef<typeof Checkbox.Root>
>(({ className, ...props }, ref) => (
  <Checkbox.Root
    ref={ref}
    className={cn(
      'h-4 w-4 rounded-sm border border-[var(--color-border-strong)] bg-[var(--color-bg-surface)]',
      'flex items-center justify-center',
      'data-[state=checked]:bg-[var(--color-action)] data-[state=checked]:border-[var(--color-action)]',
      'focus-visible:outline-none focus-visible:shadow-[var(--shadow-focus)]',
      className
    )}
    {...props}
  >
    <Checkbox.Indicator><Check size={12} className="text-white" aria-hidden="true" /></Checkbox.Indicator>
  </Checkbox.Root>
))
CheckboxImpl.displayName = 'Checkbox'

export { CheckboxImpl as Checkbox }
