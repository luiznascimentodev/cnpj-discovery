import { NavLink } from 'react-router'
import {
  BarChart3,
  Bookmark,
  LayoutGrid,
  Search,
  Settings,
} from '@/shared/ui/icons'
import { cn } from '@/shared/lib'

interface NavItem {
  to: string
  label: string
  icon: typeof Search
}

const items: readonly NavItem[] = [
  { to: '/app/prospeccao', label: 'Prospecção', icon: Search },
  { to: '/app/pipeline', label: 'Pipeline', icon: LayoutGrid },
  { to: '/app/listas', label: 'Listas salvas', icon: Bookmark },
  { to: '/app/relatorios', label: 'Relatórios', icon: BarChart3 },
  { to: '/app/configuracoes', label: 'Configurações', icon: Settings },
]

export function SideNav() {
  return (
    <nav
      aria-label="Navegação principal"
      className="flex w-60 shrink-0 flex-col gap-1 border-r border-[var(--color-border-inverse)] bg-[var(--color-bg-inverse)] px-3 py-4"
    >
      <div className="flex items-center gap-2 px-2 pb-4 pt-1">
        <span aria-hidden="true" className="inline-block h-5 w-1 rounded-sm bg-[var(--color-brand)]" />
        <span className="text-[var(--text-xs)] font-semibold uppercase tracking-wide text-[var(--color-fg-on-inverse)]">
          CNPJ Discovery
        </span>
      </div>
      {items.map(({ to, label, icon: Icon }) => (
        <NavLink
          key={to}
          to={to}
          className={({ isActive }) =>
            cn(
              'flex items-center gap-2 rounded-md px-2 py-1.5 text-[var(--text-sm)] transition-colors',
              'focus:outline-none focus-visible:ring-2 focus-visible:ring-[var(--color-focus-ring)]',
              isActive
                ? 'bg-[var(--color-bg-inverse-active)] text-[var(--color-fg-on-inverse)] font-medium'
                : 'text-[var(--color-fg-on-inverse-muted)] hover:bg-[var(--color-bg-inverse-hover)] hover:text-[var(--color-fg-on-inverse)]'
            )
          }
        >
          <Icon aria-hidden="true" className="h-4 w-4" />
          <span>{label}</span>
        </NavLink>
      ))}
    </nav>
  )
}
