import { ClosingCTA } from './sections/ClosingCTA'
import { Features } from './sections/Features'
import { Hero } from './sections/Hero'
import { MarketingFooter } from './sections/MarketingFooter'
import { MarketingHeader } from './sections/MarketingHeader'

export function LandingPage() {
  return (
    <div className="flex min-h-screen flex-col bg-[var(--color-bg-app)] text-[var(--color-fg-primary)]">
      <MarketingHeader />
      <main id="main" className="flex-1">
        <Hero />
        <Features />
        <ClosingCTA />
      </main>
      <MarketingFooter />
    </div>
  )
}
