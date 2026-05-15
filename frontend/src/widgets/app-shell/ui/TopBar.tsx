import { Bell, CircleHelp } from '@/shared/ui/icons'
import { IconButton } from '@/shared/ui/primitives/IconButton'
import { UserAvatar } from '@/entities/user'
import type { User } from '@/entities/user'

export interface TopBarProps {
  user?: User
}

export function TopBar({ user }: TopBarProps) {
  return (
    <header className="flex h-14 items-center justify-between border-b border-[var(--color-border)] bg-[var(--color-bg-surface)] px-6">
      <a
        href="#main"
        className="sr-only focus:not-sr-only focus:rounded focus:bg-[var(--color-action)] focus:px-3 focus:py-1 focus:text-white"
      >
        Pular para o conteúdo
      </a>
      <div className="text-[var(--text-sm)] font-medium text-[var(--color-fg-muted)]">
        {/* breadcrumb slot (pages may inject via outlet context futuramente) */}
      </div>
      <div className="flex items-center gap-2">
        <IconButton aria-label="Ajuda" variant="ghost">
          <CircleHelp aria-hidden="true" className="h-4 w-4" />
        </IconButton>
        <IconButton aria-label="Notificações" variant="ghost">
          <Bell aria-hidden="true" className="h-4 w-4" />
        </IconButton>
        {user && <UserAvatar user={user} size="md" />}
      </div>
    </header>
  )
}
