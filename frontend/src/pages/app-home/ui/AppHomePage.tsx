import { PageHeader } from '@/shared/ui/layout/PageHeader'
import { Stat } from '@/shared/ui/data/Stat'

export function AppHomePage() {
  return (
    <>
      <PageHeader
        title="Visão geral"
        description="Resumo das atividades de prospecção"
      />
      <div className="grid grid-cols-1 gap-4 md:grid-cols-3">
        <Stat label="Empresas no pipeline" value="—" />
        <Stat label="Listas salvas" value="—" />
        <Stat label="Buscas neste mês" value="—" />
      </div>
    </>
  )
}
