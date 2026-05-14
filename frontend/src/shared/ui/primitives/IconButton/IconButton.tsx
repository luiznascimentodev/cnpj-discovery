import { forwardRef } from 'react'
import { Button, type ButtonProps } from '../Button/Button'
import { cn } from '@/shared/lib'

export interface IconButtonProps extends Omit<ButtonProps, 'children'> {
  'aria-label': string
  children: React.ReactNode
}

export const IconButton = forwardRef<HTMLButtonElement, IconButtonProps>(
  ({ className, size = 'md', ...props }, ref) => {
    const dim = size === 'sm' ? 'h-8 w-8' : size === 'lg' ? 'h-12 w-12' : 'h-10 w-10'
    return <Button ref={ref} size={size} className={cn(dim, 'p-0', className)} {...props} />
  }
)
IconButton.displayName = 'IconButton'
