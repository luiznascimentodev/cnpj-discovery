import { Link } from 'react-router'
import { Button } from '@/shared/ui/primitives/Button'
import { Container } from '@/shared/ui/layout/Container'
import { Stack } from '@/shared/ui/layout/Stack'
import { ProductMockup } from '../mockups/ProductMockup'

export function Hero() {
  return (
    <section
      aria-labelledby="hero-title"
      className="border-b border-[var(--color-border)] bg-gradient-to-b from-[var(--color-bg-surface)] to-[var(--color-bg-app)]"
    >
      <Container size="lg" className="py-16 lg:py-24">
        <div className="grid items-center gap-10 lg:grid-cols-[minmax(0,1fr)_minmax(0,1fr)] lg:gap-16">
          <Stack gap={6} align="start">
            <span className="rounded-full bg-[var(--color-info-bg)] px-3 py-1 text-[var(--text-xs)] font-medium text-[var(--color-info-fg)]">
              Dados oficiais da Receita Federal
            </span>
            <h1
              id="hero-title"
              className="text-[40px] leading-tight font-semibold tracking-tight lg:text-[48px]"
            >
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
          <div className="hidden lg:block">
            <ProductMockup />
          </div>
        </div>
      </Container>
    </section>
  )
}
