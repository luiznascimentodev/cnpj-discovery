import * as Popover from '@radix-ui/react-popover'
import { forwardRef } from 'react'
import { cn } from '@/shared/lib'

export const PopoverRoot = Popover.Root
export const PopoverTrigger = Popover.Trigger
export const PopoverClose = Popover.Close
export const PopoverAnchor = Popover.Anchor

export const PopoverContent = forwardRef<
  React.ElementRef<typeof Popover.Content>,
  React.ComponentPropsWithoutRef<typeof Popover.Content>
>(({ className, align = 'center', sideOffset = 6, ...props }, ref) => (
  <Popover.Portal>
    <Popover.Content
      ref={ref}
      align={align}
      sideOffset={sideOffset}
      className={cn(
        'z-[var(--z-popover)] w-72 rounded-lg bg-[var(--color-bg-surface)] border border-[var(--color-border)]',
        'p-3 shadow-[var(--shadow-md)] outline-none',
        className
      )}
      {...props}
    />
  </Popover.Portal>
))
PopoverContent.displayName = 'PopoverContent'
