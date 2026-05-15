import { useEffect } from 'react'
import { Link, useSearchParams } from 'react-router'
import { ApiError } from '@/shared/api'
import { useVerifyEmail } from '@/features/auth'
import { Button } from '@/shared/ui/primitives/Button'
import { Container } from '@/shared/ui/layout/Container'
import { Spinner } from '@/shared/ui/primitives/Spinner'

export function VerificarEmailPage() {
  const [params] = useSearchParams()
  const token = params.get('token') || ''
  const verify = useVerifyEmail()
  const error = verify.error instanceof ApiError ? verify.error.message : null

  useEffect(() => {
    if (token && verify.isIdle) {
      verify.mutate(token)
    }
  }, [token, verify])

  return (
    <div className="min-h-screen bg-[var(--color-bg-app)] py-12">
      <Container size="sm">
        <div className="rounded-xl border border-[var(--color-border)] bg-[var(--color-bg-surface)] p-8 shadow-sm">
          <h1 className="text-[var(--text-xl)] font-semibold text-[var(--color-fg-primary)]">
            Verificação de e-mail
          </h1>
          <div className="mt-4 text-[var(--text-sm)] text-[var(--color-fg-muted)]">
            {!token ? <p>Token ausente.</p> : null}
            {verify.isPending ? (
              <div className="flex items-center gap-2">
                <Spinner />
                <span>Verificando...</span>
              </div>
            ) : null}
            {verify.data ? <p className="text-[var(--color-success-fg)]">{verify.data.message}</p> : null}
            {error ? <p className="text-[var(--color-danger-fg)]">{error}</p> : null}
          </div>
          <div className="mt-6">
            <Button asChild>
              <Link to="/login">Entrar</Link>
            </Button>
          </div>
        </div>
      </Container>
    </div>
  )
}
