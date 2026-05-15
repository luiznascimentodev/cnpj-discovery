import * as Tooltip from '@radix-ui/react-tooltip'
import { forwardRef } from 'react'
import { cn } from '@/shared/lib'

export const TooltipProvider = Tooltip.Provider
export const TooltipRoot = Tooltip.Root
export const TooltipTrigger = Tooltip.Trigger

export const TooltipContent = forwardRef<
  React.ElementRef<typeof Tooltip.Content>,
  React.ComponentPropsWithoutRef<typeof Tooltip.Content>
>(({ className, sideOffset = 4, ...props }, ref) => (
  <Tooltip.Portal>
    <Tooltip.Content
      ref={ref}
      sideOffset={sideOffset}
      className={cn(
        'z-[var(--z-tooltip)] rounded-md bg-[var(--color-gray-900)] text-white',
        'px-2 py-1 text-[var(--text-xs)] shadow-[var(--shadow-md)]',
        'data-[state=open]:animate-in data-[state=closed]:animate-out',
        className
      )}
      {...props}
    />
  </Tooltip.Portal>
))
TooltipContent.displayName = 'TooltipContent'
