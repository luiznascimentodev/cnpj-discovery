import { Link } from 'react-router'
import { Container } from '@/shared/ui/layout/Container'

const WHATSAPP_HREF = 'https://wa.me/5541984821206'
const LINKEDIN_HREF = 'https://www.linkedin.com/in/luiz-felippe-nascimento/'
const PORTFOLIO_HREF = 'https://luiznascimento.dev.br/'

export function MarketingFooter() {
  return (
    <footer className="border-t border-[var(--color-border)] bg-[var(--color-bg-surface)]">
      <Container size="lg" className="flex flex-col gap-6 py-8 lg:flex-row lg:items-start lg:justify-between">
        <div className="space-y-1">
          <div className="text-[var(--text-sm)] font-semibold text-[var(--color-fg-primary)]">
            CNPJ Discovery
          </div>
          <div className="text-[var(--text-xs)] text-[var(--color-fg-muted)]">
            Criado por{' '}
            <a
              href={PORTFOLIO_HREF}
              target="_blank"
              rel="noopener noreferrer"
              className="font-medium text-[var(--color-fg-secondary)] hover:text-[var(--color-action)]"
            >
              Luiz Nascimento
            </a>
            {' · © '}
            {new Date().getFullYear()}
          </div>
        </div>

        <nav aria-label="Institucional" className="flex flex-col gap-2 text-[var(--text-xs)] lg:items-end">
          <div className="flex items-center gap-3">
            <Link
              to="/termos"
              className="text-[var(--color-fg-muted)] hover:text-[var(--color-fg-primary)]"
            >
              Termos de uso
            </Link>
            <span aria-hidden="true" className="text-[var(--color-fg-muted)]">·</span>
            <Link
              to="/privacidade"
              className="text-[var(--color-fg-muted)] hover:text-[var(--color-fg-primary)]"
            >
              Privacidade
            </Link>
            <span aria-hidden="true" className="text-[var(--color-fg-muted)]">·</span>
            <a
              href={WHATSAPP_HREF}
              target="_blank"
              rel="noopener noreferrer"
              className="text-[var(--color-fg-muted)] hover:text-[var(--color-fg-primary)]"
            >
              Contato
            </a>
          </div>
          <div className="flex items-center gap-3">
            <a
              href={LINKEDIN_HREF}
              target="_blank"
              rel="noopener noreferrer"
              className="text-[var(--color-fg-muted)] hover:text-[var(--color-fg-primary)]"
            >
              LinkedIn
            </a>
            <span aria-hidden="true" className="text-[var(--color-fg-muted)]">·</span>
            <a
              href={PORTFOLIO_HREF}
              target="_blank"
              rel="noopener noreferrer"
              className="text-[var(--color-fg-muted)] hover:text-[var(--color-fg-primary)]"
            >
              Portfólio
            </a>
          </div>
        </nav>
      </Container>
    </footer>
  )
}
