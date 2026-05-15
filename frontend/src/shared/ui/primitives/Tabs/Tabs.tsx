import * as Tabs from '@radix-ui/react-tabs'
import { forwardRef } from 'react'
import { cn } from '@/shared/lib'

export const TabsRoot = Tabs.Root

export const TabsList = forwardRef<
  React.ElementRef<typeof Tabs.List>,
  React.ComponentPropsWithoutRef<typeof Tabs.List>
>(({ className, ...props }, ref) => (
  <Tabs.List
    ref={ref}
    className={cn('inline-flex items-center gap-1 border-b border-[var(--color-border)]', className)}
    {...props}
  />
))
TabsList.displayName = 'TabsList'

export const TabsTrigger = forwardRef<
  React.ElementRef<typeof Tabs.Trigger>,
  React.ComponentPropsWithoutRef<typeof Tabs.Trigger>
>(({ className, ...props }, ref) => (
  <Tabs.Trigger
    ref={ref}
    className={cn(
      'px-4 h-10 text-[var(--text-sm)] font-medium text-[var(--color-fg-secondary)]',
      'border-b-2 border-transparent -mb-px',
      'data-[state=active]:text-[var(--color-action)] data-[state=active]:border-[var(--color-action)]',
      'focus-visible:outline-none focus-visible:shadow-[var(--shadow-focus)] rounded-t-md',
      className
    )}
    {...props}
  />
))
TabsTrigger.displayName = 'TabsTrigger'

export const TabsContent = Tabs.Content
