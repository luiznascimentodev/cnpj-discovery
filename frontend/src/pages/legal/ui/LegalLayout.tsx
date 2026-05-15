import { type ReactNode } from 'react'
import { MarketingFooter } from '@/pages/landing/ui/sections/MarketingFooter'
import { MarketingHeader } from '@/pages/landing/ui/sections/MarketingHeader'
import { Container } from '@/shared/ui/layout/Container'

type LegalLayoutProps = {
  title: string
  lastUpdated: string
  children: ReactNode
}

export function LegalLayout({ title, lastUpdated, children }: LegalLayoutProps) {
  return (
    <div className="flex min-h-screen flex-col bg-[var(--color-bg-app)] text-[var(--color-fg-primary)]">
      <MarketingHeader />
      <main id="main" className="flex-1">
        <Container size="md" className="py-12 lg:py-16">
          <header className="mb-10 border-b border-[var(--color-border)] pb-6">
            <h1 className="text-[var(--text-3xl)] font-semibold tracking-tight">{title}</h1>
            <p className="mt-2 text-[var(--text-sm)] text-[var(--color-fg-muted)]">
              Última atualização: {lastUpdated}
            </p>
          </header>
          <article className="space-y-8 text-[var(--text-base)] leading-relaxed text-[var(--color-fg-primary)]">
            {children}
          </article>
        </Container>
      </main>
      <MarketingFooter />
    </div>
  )
}
