import * as Separator from '@radix-ui/react-separator'
import { forwardRef } from 'react'
import { cn } from '@/shared/lib'

const SeparatorImpl = forwardRef<
  React.ElementRef<typeof Separator.Root>,
  React.ComponentPropsWithoutRef<typeof Separator.Root>
>(({ className, orientation = 'horizontal', decorative = true, ...props }, ref) => (
  <Separator.Root
    ref={ref}
    orientation={orientation}
    decorative={decorative}
    className={cn(
      'bg-[var(--color-border)]',
      orientation === 'horizontal' ? 'h-px w-full' : 'h-full w-px',
      className
    )}
    {...props}
  />
))
SeparatorImpl.displayName = 'Separator'

export { SeparatorImpl as Separator }
