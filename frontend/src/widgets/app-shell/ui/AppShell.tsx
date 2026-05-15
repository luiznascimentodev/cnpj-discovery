import { Outlet } from 'react-router'
import { SideNav } from './SideNav'
import { TopBar } from './TopBar'
import type { User } from '@/entities/user'

export interface AppShellProps {
  user?: User
}

export function AppShell({ user }: AppShellProps) {
  return (
    <div className="flex min-h-screen w-full bg-[var(--color-bg-app)] text-[var(--color-fg-primary)]">
      <SideNav />
      <div className="flex min-w-0 flex-1 flex-col">
        <TopBar user={user} />
        <main id="main" className="flex-1 overflow-auto px-6 py-6">
          <Outlet />
        </main>
      </div>
    </div>
  )
}
