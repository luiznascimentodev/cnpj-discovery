import { Link } from 'react-router'
import { Button } from '@/shared/ui/primitives/Button'
import { Container } from '@/shared/ui/layout/Container'

export function MarketingHeader() {
  return (
    <header className="sticky top-0 z-10 border-b border-[var(--color-border)] bg-[var(--color-bg-surface)]/95 backdrop-blur">
      <Container size="lg" className="flex h-14 items-center justify-between">
        <Link
          to="/"
          className="text-[var(--text-base)] font-semibold tracking-tight text-[var(--color-fg-primary)]"
        >
          CNPJ Discovery
        </Link>
        <nav className="flex items-center gap-2" aria-label="Acesso">
          <Button asChild variant="ghost">
            <Link to="/login">Entrar</Link>
          </Button>
          <Button asChild>
            <Link to="/registro">Criar conta</Link>
          </Button>
        </nav>
      </Container>
    </header>
  )
}
