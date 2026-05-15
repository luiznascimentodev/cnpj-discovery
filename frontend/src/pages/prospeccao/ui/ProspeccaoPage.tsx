import { PageHeader } from '@/shared/ui/layout/PageHeader'

export function ProspeccaoPage() {
  return (
    <>
      <PageHeader
        title="Prospecção"
        description="Busque empresas pelos filtros oficiais da Receita Federal"
      />
      <div className="rounded-lg border border-[var(--color-border)] bg-[var(--color-bg-surface)] p-6">
        <p className="text-[var(--text-sm)] text-[var(--color-fg-muted)]">
          Migração do módulo legado em andamento (Fase 14).
        </p>
      </div>
    </>
  )
}
