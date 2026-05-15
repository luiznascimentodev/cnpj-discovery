import * as Select from '@radix-ui/react-select'
import { forwardRef } from 'react'
import { Check, ChevronDown } from '@/shared/ui/icons'
import { cn } from '@/shared/lib'

export const SelectRoot = Select.Root
export const SelectValue = Select.Value

export const SelectTrigger = forwardRef<
  React.ElementRef<typeof Select.Trigger>,
  React.ComponentPropsWithoutRef<typeof Select.Trigger>
>(({ className, children, ...props }, ref) => (
  <Select.Trigger
    ref={ref}
    className={cn(
      'flex h-10 w-full items-center justify-between rounded-md border border-[var(--color-border-strong)]',
      'bg-[var(--color-bg-surface)] px-3 text-[var(--text-base)] outline-none',
      'focus-visible:shadow-[var(--shadow-focus)] disabled:opacity-50',
      className
    )}
    {...props}
  >
    {children}
    <Select.Icon><ChevronDown size={16} aria-hidden="true" /></Select.Icon>
  </Select.Trigger>
))
SelectTrigger.displayName = 'SelectTrigger'

export const SelectContent = forwardRef<
  React.ElementRef<typeof Select.Content>,
  React.ComponentPropsWithoutRef<typeof Select.Content>
>(({ className, children, ...props }, ref) => (
  <Select.Portal>
    <Select.Content
      ref={ref}
      className={cn(
        'z-[var(--z-dropdown)] rounded-lg border border-[var(--color-border)] bg-[var(--color-bg-surface)]',
        'shadow-[var(--shadow-md)] overflow-hidden',
        className
      )}
      position="popper"
      {...props}
    >
      <Select.Viewport className="p-1">{children}</Select.Viewport>
    </Select.Content>
  </Select.Portal>
))
SelectContent.displayName = 'SelectContent'

export const SelectItem = forwardRef<
  React.ElementRef<typeof Select.Item>,
  React.ComponentPropsWithoutRef<typeof Select.Item>
>(({ className, children, ...props }, ref) => (
  <Select.Item
    ref={ref}
    className={cn(
      'flex items-center justify-between rounded-md px-2.5 py-2 text-[var(--text-sm)] outline-none',
      'data-[highlighted]:bg-[var(--color-bg-subtle)] cursor-pointer',
      className
    )}
    {...props}
  >
    <Select.ItemText>{children}</Select.ItemText>
    <Select.ItemIndicator><Check size={14} aria-hidden="true" /></Select.ItemIndicator>
  </Select.Item>
))
SelectItem.displayName = 'SelectItem'
