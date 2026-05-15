import { PageHeader } from '@/shared/ui/layout/PageHeader'

export function ConfiguracoesPage() {
  return (
    <>
      <PageHeader title="Configurações" description="Conta, preferências e equipe" />
      <div className="rounded-lg border border-[var(--color-border)] bg-[var(--color-bg-surface)] p-6">
        <p className="text-[var(--text-sm)] text-[var(--color-fg-muted)]">
          Em breve: gerenciar sessão, preferências de notificação e integrações.
        </p>
      </div>
    </>
  )
}
