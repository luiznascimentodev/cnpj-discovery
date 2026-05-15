import { type HTMLAttributes, forwardRef } from 'react'
import { cn } from '@/shared/lib'

const gapClasses = {
  0: 'gap-0',
  1: 'gap-1',
  2: 'gap-2',
  3: 'gap-3',
  4: 'gap-4',
  5: 'gap-5',
  6: 'gap-6',
} as const

export interface InlineProps extends HTMLAttributes<HTMLDivElement> {
  gap?: keyof typeof gapClasses
  align?: 'start' | 'center' | 'end' | 'baseline'
  justify?: 'start' | 'center' | 'end' | 'between'
  wrap?: boolean
}

const alignClasses = { start: 'items-start', center: 'items-center', end: 'items-end', baseline: 'items-baseline' }
const justifyClasses = { start: 'justify-start', center: 'justify-center', end: 'justify-end', between: 'justify-between' }

export const Inline = forwardRef<HTMLDivElement, InlineProps>(function Inline(
  { className, gap = 2, align = 'center', justify = 'start', wrap = false, ...rest },
  ref
) {
  return (
    <div
      ref={ref}
      className={cn(
        'flex',
        wrap && 'flex-wrap',
        gapClasses[gap],
        alignClasses[align],
        justifyClasses[justify],
        className
      )}
      {...rest}
    />
  )
})
