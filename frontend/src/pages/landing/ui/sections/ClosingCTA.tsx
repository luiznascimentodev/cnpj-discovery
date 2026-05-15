import { Link } from 'react-router'
import { Button } from '@/shared/ui/primitives/Button'
import { Container } from '@/shared/ui/layout/Container'

export function ClosingCTA() {
  return (
    <section
      aria-labelledby="closing-cta-title"
      className="bg-[var(--color-bg-inverse)] text-[var(--color-fg-on-inverse)]"
    >
      <Container size="lg" className="flex flex-col items-start gap-6 py-14 lg:flex-row lg:items-center lg:justify-between">
        <div className="max-w-2xl">
          <h2 id="closing-cta-title" className="text-[var(--text-2xl)] font-semibold tracking-tight">
            Pronto para parar de prospectar no escuro?
          </h2>
          <p className="mt-2 text-[var(--text-base)] text-[var(--color-fg-on-inverse-muted)]">
            Crie sua conta em menos de um minuto e comece a explorar a base de CNPJs hoje mesmo.
          </p>
        </div>
        <Button
          asChild
          size="lg"
          className="bg-[var(--color-brand)] text-[var(--color-brand-fg)] hover:bg-[var(--color-yellow-400)]"
        >
          <Link to="/registro">Criar conta grátis</Link>
        </Button>
      </Container>
    </section>
  )
}
