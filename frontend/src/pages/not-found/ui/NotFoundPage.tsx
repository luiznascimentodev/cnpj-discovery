import { Link } from 'react-router'
import { Button } from '@/shared/ui/primitives/Button'

export function NotFoundPage() {
  return (
    <div className="flex min-h-screen items-center justify-center bg-[var(--color-bg-app)] px-6">
      <div className="max-w-md text-center">
        <p className="text-[var(--text-sm)] font-semibold uppercase tracking-wide text-[var(--color-fg-muted)]">
          404
        </p>
        <h1 className="mt-2 text-[var(--text-2xl)] font-semibold text-[var(--color-fg-primary)]">
          Página não encontrada
        </h1>
        <p className="mt-2 text-[var(--text-sm)] text-[var(--color-fg-muted)]">
          O endereço que você acessou não existe ou foi movido.
        </p>
        <div className="mt-6">
          <Button asChild>
            <Link to="/">Voltar ao início</Link>
          </Button>
        </div>
      </div>
    </div>
  )
}
