import { Avatar, AvatarFallback, AvatarImage } from '@/shared/ui/primitives/Avatar'
import { userInitials } from '../../lib/userInitials'
import type { User } from '../../model/types'

export interface UserAvatarProps {
  user: Pick<User, 'name' | 'avatarUrl'>
  size?: 'sm' | 'md' | 'lg'
}

const sizeClasses = { sm: 'h-6 w-6 text-[10px]', md: 'h-8 w-8 text-xs', lg: 'h-10 w-10 text-sm' } as const

export function UserAvatar({ user, size = 'md' }: UserAvatarProps) {
  return (
    <Avatar className={sizeClasses[size]}>
      {user.avatarUrl && <AvatarImage src={user.avatarUrl} alt={user.name} />}
      <AvatarFallback>{userInitials(user.name)}</AvatarFallback>
    </Avatar>
  )
}
