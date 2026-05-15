import { Navigate, Outlet, useLocation } from 'react-router'

/**
 * Stub: real auth wiring comes in a later subproject.
 * For now, allows all access — toggling AUTH_ENABLED makes it redirect to /login.
 */
const AUTH_ENABLED = false

export function ProtectedRoute() {
  const location = useLocation()
  if (AUTH_ENABLED) {
    return <Navigate to="/login" replace state={{ from: location }} />
  }
  return <Outlet />
}
