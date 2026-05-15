import { type ReactNode } from 'react'

type LegalSectionProps = {
  id?: string
  title: string
  children: ReactNode
}

export function LegalSection({ id, title, children }: LegalSectionProps) {
  return (
    <section id={id} aria-labelledby={id ? `${id}-title` : undefined}>
      <h2
        id={id ? `${id}-title` : undefined}
        className="mb-3 text-[var(--text-xl)] font-semibold tracking-tight"
      >
        {title}
      </h2>
      <div className="space-y-3 text-[var(--color-fg-secondary)]">{children}</div>
    </section>
  )
}
