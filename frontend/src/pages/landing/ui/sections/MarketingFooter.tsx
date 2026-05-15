import { Container } from '@/shared/ui/layout/Container'

export function MarketingFooter() {
  return (
    <footer className="border-t border-[var(--color-border)] bg-[var(--color-bg-surface)]">
      <Container size="lg" className="flex flex-col items-start justify-between gap-3 py-6 md:flex-row md:items-center">
        <div className="text-[var(--text-xs)] text-[var(--color-fg-muted)]">
          CNPJ Discovery · © {new Date().getFullYear()}
        </div>
        <nav aria-label="Institucional" className="flex items-center gap-4 text-[var(--text-xs)]">
          <a
            href="mailto:contato@cnpj-discovery.com.br"
            className="text-[var(--color-fg-muted)] hover:text-[var(--color-fg-primary)]"
          >
            Contato
          </a>
          <span aria-hidden="true" className="text-[var(--color-fg-muted)]">·</span>
          <span className="text-[var(--color-fg-muted)]">Termos</span>
          <span aria-hidden="true" className="text-[var(--color-fg-muted)]">·</span>
          <span className="text-[var(--color-fg-muted)]">Privacidade</span>
        </nav>
      </Container>
    </footer>
  )
}
