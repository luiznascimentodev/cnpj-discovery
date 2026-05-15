import { type HTMLAttributes, forwardRef } from 'react'
import { cn } from '@/shared/lib'

const sizeClasses = {
  sm: 'max-w-3xl',
  md: 'max-w-5xl',
  lg: 'max-w-7xl',
  full: 'max-w-none',
} as const

export interface ContainerProps extends HTMLAttributes<HTMLDivElement> {
  size?: keyof typeof sizeClasses
}

export const Container = forwardRef<HTMLDivElement, ContainerProps>(function Container(
  { className, size = 'lg', ...rest },
  ref
) {
  return (
    <div ref={ref} className={cn('mx-auto w-full px-6', sizeClasses[size], className)} {...rest} />
  )
})
