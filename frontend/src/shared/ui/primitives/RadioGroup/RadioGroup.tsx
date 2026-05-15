import * as RadioGroup from '@radix-ui/react-radio-group'
import { forwardRef } from 'react'
import { cn } from '@/shared/lib'

export const RadioGroupRoot = RadioGroup.Root

export const RadioGroupItem = forwardRef<
  React.ElementRef<typeof RadioGroup.Item>,
  React.ComponentPropsWithoutRef<typeof RadioGroup.Item>
>(({ className, ...props }, ref) => (
  <RadioGroup.Item
    ref={ref}
    className={cn(
      'h-4 w-4 rounded-full border border-[var(--color-border-strong)] bg-[var(--color-bg-surface)]',
      'data-[state=checked]:border-[var(--color-action)] flex items-center justify-center',
      'focus-visible:outline-none focus-visible:shadow-[var(--shadow-focus)]',
      className
    )}
    {...props}
  >
    <RadioGroup.Indicator className="h-2 w-2 rounded-full bg-[var(--color-action)]" />
  </RadioGroup.Item>
))
RadioGroupItem.displayName = 'RadioGroupItem'
