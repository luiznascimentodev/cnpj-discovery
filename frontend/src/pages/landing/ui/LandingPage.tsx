import { Link } from 'react-router'
import { Button } from '@/shared/ui/primitives/Button'
import { Container } from '@/shared/ui/layout/Container'
import { Stack } from '@/shared/ui/layout/Stack'

export function LandingPage() {
  return (
    <div className="min-h-screen bg-[var(--color-bg-app)] text-[var(--color-fg-primary)]">
      <header className="border-b border-[var(--color-border)] bg-[var(--color-bg-surface)]">
        <Container size="lg" className="flex h-14 items-center justify-between">
          <div className="text-[var(--text-base)] font-semibold">CNPJ Discovery</div>
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
      <main>
        <section className="border-b border-[var(--color-border)] bg-gradient-to-b from-[var(--color-bg-surface)] to-[var(--color-bg-app)]">
          <Container size="lg" className="py-20">
            <Stack gap={6} align="start" className="max-w-2xl">
              <span className="rounded-full bg-[var(--color-info-bg)] px-3 py-1 text-[var(--text-xs)] font-medium text-[var(--color-info-fg)]">
                Dados oficiais da Receita Federal
              </span>
              <h1 className="text-[40px] leading-tight font-semibold tracking-tight">
                Prospecção B2B com a base completa do CNPJ brasileiro.
              </h1>
              <p className="text-[var(--text-lg)] text-[var(--color-fg-muted)]">
                Filtre, segmente e organize empresas em pipeline com a precisão dos dados oficiais — sem
                planilhas, sem retrabalho.
              </p>
              <div className="flex gap-2">
                <Button asChild size="lg">
                  <Link to="/registro">Começar gratuitamente</Link>
                </Button>
                <Button asChild variant="secondary" size="lg">
                  <Link to="/login">Já tenho conta</Link>
                </Button>
              </div>
            </Stack>
          </Container>
        </section>
      </main>
    </div>
  )
}
