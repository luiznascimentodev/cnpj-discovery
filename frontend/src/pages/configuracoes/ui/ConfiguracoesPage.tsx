import { useNavigate } from 'react-router'
import { useLogout, useSession } from '@/features/auth'
import { PageHeader } from '@/shared/ui/layout/PageHeader'
import { Button } from '@/shared/ui/primitives/Button'

export function ConfiguracoesPage() {
  const navigate = useNavigate()
  const session = useSession()
  const logout = useLogout()

  const handleLogout = async () => {
    await logout.mutateAsync()
    navigate('/login', { replace: true })
  }

  return (
    <>
      <PageHeader title="Configurações" description="Conta, preferências e equipe" />
      <div className="rounded-lg border border-[var(--color-border)] bg-[var(--color-bg-surface)] p-6">
        <div className="flex flex-col gap-4 sm:flex-row sm:items-center sm:justify-between">
          <div>
            <h2 className="text-[var(--text-base)] font-semibold text-[var(--color-fg-primary)]">
              Sessão
            </h2>
            <p className="mt-1 text-[var(--text-sm)] text-[var(--color-fg-muted)]">
              {session.data?.email ?? 'Conta autenticada'}
            </p>
          </div>
          <Button variant="secondary" onClick={handleLogout} disabled={logout.isPending}>
            {logout.isPending ? 'Saindo...' : 'Sair'}
          </Button>
        </div>
      </div>
    </>
  )
}
