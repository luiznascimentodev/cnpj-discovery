import * as Switch from '@radix-ui/react-switch'
import { forwardRef } from 'react'
import { cn } from '@/shared/lib'

const SwitchImpl = forwardRef<
  React.ElementRef<typeof Switch.Root>,
  React.ComponentPropsWithoutRef<typeof Switch.Root>
>(({ className, ...props }, ref) => (
  <Switch.Root
    ref={ref}
    className={cn(
      'h-5 w-9 rounded-full bg-[var(--color-gray-300)] relative transition-colors',
      'data-[state=checked]:bg-[var(--color-action)]',
      'focus-visible:outline-none focus-visible:shadow-[var(--shadow-focus)]',
      className
    )}
    {...props}
  >
    <Switch.Thumb className="block h-4 w-4 bg-white rounded-full shadow translate-x-0.5 transition-transform data-[state=checked]:translate-x-4" />
  </Switch.Root>
))
SwitchImpl.displayName = 'Switch'

export { SwitchImpl as Switch }
