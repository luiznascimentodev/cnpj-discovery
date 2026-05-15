import { Filter, KanbanSquare, RefreshCw } from '@/shared/ui/icons'
import { Container } from '@/shared/ui/layout/Container'

type FeatureProps = {
  icon: React.ComponentType<{ className?: string; 'aria-hidden'?: boolean }>
  title: string
  description: string
}

const FEATURES: FeatureProps[] = [
  {
    icon: Filter,
    title: 'Filtros precisos',
    description:
      'CNAE, porte, UF, bairro, capital social, situação cadastral. Combine como quiser para encontrar a empresa certa.',
  },
  {
    icon: KanbanSquare,
    title: 'Pipeline de prospecção',
    description:
      'Organize empresas em estágios, anote contatos e mantenha cada lead em movimento. Nada de planilhas paralelas.',
  },
  {
    icon: RefreshCw,
    title: 'Dados sempre atualizados',
    description:
      'Base sincronizada com a Receita Federal a cada release oficial. Você sempre prospecta na versão atual da realidade.',
  },
]

export function Features() {
  return (
    <section
      aria-labelledby="features-title"
      className="border-b border-[var(--color-border)] bg-[var(--color-bg-app)]"
    >
      <Container size="lg" className="py-16">
        <h2
          id="features-title"
          className="mb-10 max-w-2xl text-[var(--text-2xl)] font-semibold tracking-tight"
        >
          Tudo que você precisa para prospectar com confiança.
        </h2>
        <div className="grid gap-6 lg:grid-cols-3 lg:gap-8">
          {FEATURES.map((feature) => (
            <FeatureCard key={feature.title} {...feature} />
          ))}
        </div>
      </Container>
    </section>
  )
}

function FeatureCard({ icon: Icon, title, description }: FeatureProps) {
  return (
    <article className="rounded-[var(--radius-lg)] border border-[var(--color-border)] bg-[var(--color-bg-surface)] p-6 shadow-[var(--shadow-sm)]">
      <div className="mb-4 inline-flex h-10 w-10 items-center justify-center rounded-[var(--radius-md)] bg-[var(--color-info-bg)] text-[var(--color-info-fg)]">
        <Icon className="h-5 w-5" aria-hidden />
      </div>
      <h3 className="mb-2 text-[var(--text-md)] font-semibold tracking-tight">{title}</h3>
      <p className="text-[var(--text-base)] text-[var(--color-fg-muted)]">{description}</p>
    </article>
  )
}
