import * as DropdownMenu from '@radix-ui/react-dropdown-menu'
import { forwardRef } from 'react'
import { cn } from '@/shared/lib'

export const DropdownMenuRoot = DropdownMenu.Root
export const DropdownMenuTrigger = DropdownMenu.Trigger
export const DropdownMenuLabel = DropdownMenu.Label
export const DropdownMenuSeparator = DropdownMenu.Separator

export const DropdownMenuContent = forwardRef<
  React.ElementRef<typeof DropdownMenu.Content>,
  React.ComponentPropsWithoutRef<typeof DropdownMenu.Content>
>(({ className, sideOffset = 4, ...props }, ref) => (
  <DropdownMenu.Portal>
    <DropdownMenu.Content
      ref={ref}
      sideOffset={sideOffset}
      className={cn(
        'z-[var(--z-dropdown)] min-w-[10rem] rounded-lg bg-[var(--color-bg-surface)]',
        'border border-[var(--color-border)] p-1 shadow-[var(--shadow-md)]',
        className
      )}
      {...props}
    />
  </DropdownMenu.Portal>
))
DropdownMenuContent.displayName = 'DropdownMenuContent'

export const DropdownMenuItem = forwardRef<
  React.ElementRef<typeof DropdownMenu.Item>,
  React.ComponentPropsWithoutRef<typeof DropdownMenu.Item>
>(({ className, ...props }, ref) => (
  <DropdownMenu.Item
    ref={ref}
    className={cn(
      'flex items-center gap-2 rounded-md px-2.5 py-2 text-[var(--text-sm)] cursor-pointer outline-none',
      'data-[highlighted]:bg-[var(--color-bg-subtle)]',
      className
    )}
    {...props}
  />
))
DropdownMenuItem.displayName = 'DropdownMenuItem'
