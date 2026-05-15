import { PageHeader } from '@/shared/ui/layout/PageHeader'
import { EmptyState } from '@/shared/ui/data/EmptyState'
import { BarChart3 } from '@/shared/ui/icons'

export function RelatoriosPage() {
  return (
    <>
      <PageHeader title="Relatórios" description="Análises sobre seu funil e prospecções" />
      <EmptyState
        icon={BarChart3}
        title="Sem dados suficientes"
        description="Adicione empresas ao pipeline para ver relatórios."
      />
    </>
  )
}
