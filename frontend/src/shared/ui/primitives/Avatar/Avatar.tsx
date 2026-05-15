import * as Avatar from '@radix-ui/react-avatar'
import { forwardRef } from 'react'
import { cn } from '@/shared/lib'

export interface AvatarRootProps extends React.ComponentPropsWithoutRef<typeof Avatar.Root> {
  size?: 'sm' | 'md' | 'lg'
}

const AvatarImpl = forwardRef<React.ElementRef<typeof Avatar.Root>, AvatarRootProps>(
  ({ className, size = 'md', ...props }, ref) => {
    const dim =
      size === 'sm' ? 'h-7 w-7 text-[10px]'
      : size === 'lg' ? 'h-10 w-10 text-[13px]'
      : 'h-8 w-8 text-[11px]'
    return (
      <Avatar.Root
        ref={ref}
        className={cn(
          'inline-flex items-center justify-center overflow-hidden rounded-full bg-[var(--color-yellow-500)] text-[var(--color-gray-900)] font-semibold',
          dim,
          className
        )}
        {...props}
      />
    )
  }
)
AvatarImpl.displayName = 'Avatar'

export { AvatarImpl as Avatar }
export const AvatarImage = Avatar.Image
export const AvatarFallback = Avatar.Fallback
