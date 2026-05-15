import { Navigate, Outlet, useLocation } from 'react-router'
import { useSession } from '@/features/auth'
import { Spinner } from '@/shared/ui/primitives/Spinner'

export function ProtectedRoute() {
  const location = useLocation()
  const session = useSession()

  if (session.isPending) {
    return (
      <div className="flex min-h-screen items-center justify-center bg-[var(--color-bg-app)]">
        <Spinner size={32} />
      </div>
    )
  }

  if (session.isError) {
    const next = encodeURIComponent(`${location.pathname}${location.search}`)
    return <Navigate to={`/login?next=${next}`} replace />
  }

  return <Outlet />
}
