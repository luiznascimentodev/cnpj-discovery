import { isRouteErrorResponse, Link, useRouteError } from 'react-router'
import { Button } from '@/shared/ui/primitives/Button'
import { Container } from '@/shared/ui/layout/Container'

export function RouteErrorBoundary() {
  const error = useRouteError()
  const status = isRouteErrorResponse(error) ? error.status : 500
  const title =
    status === 404
      ? 'Página não encontrada'
      : status === 403
        ? 'Acesso negado'
        : 'Algo deu errado'
  const description =
    status === 404
      ? 'O endereço que você acessou não existe ou foi movido.'
      : 'Tente novamente em alguns instantes. Se persistir, entre em contato com o suporte.'

  return (
    <div className="flex min-h-screen items-center justify-center bg-[var(--color-bg-app)] px-6">
      <Container size="sm" className="text-center">
        <p className="text-[var(--text-sm)] font-semibold uppercase tracking-wide text-[var(--color-fg-muted)]">
          Erro {status}
        </p>
        <h1 className="mt-2 text-[var(--text-2xl)] font-semibold text-[var(--color-fg-primary)]">
          {title}
        </h1>
        <p className="mt-2 text-[var(--text-sm)] text-[var(--color-fg-muted)]">{description}</p>
        <div className="mt-6">
          <Button asChild>
            <Link to="/">Voltar ao início</Link>
          </Button>
        </div>
      </Container>
    </div>
  )
}
