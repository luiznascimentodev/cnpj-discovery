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
  8: 'gap-8',
} as const

export interface StackProps extends HTMLAttributes<HTMLDivElement> {
  gap?: keyof typeof gapClasses
  align?: 'start' | 'center' | 'end' | 'stretch'
  justify?: 'start' | 'center' | 'end' | 'between'
}

const alignClasses = { start: 'items-start', center: 'items-center', end: 'items-end', stretch: 'items-stretch' }
const justifyClasses = { start: 'justify-start', center: 'justify-center', end: 'justify-end', between: 'justify-between' }

export const Stack = forwardRef<HTMLDivElement, StackProps>(function Stack(
  { className, gap = 4, align = 'stretch', justify = 'start', ...rest },
  ref
) {
  return (
    <div
      ref={ref}
      className={cn(
        'flex flex-col',
        gapClasses[gap],
        alignClasses[align],
        justifyClasses[justify],
        className
      )}
      {...rest}
    />
  )
})
