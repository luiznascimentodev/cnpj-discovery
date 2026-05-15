import { PageHeader } from '@/shared/ui/layout/PageHeader'
import { EmptyState } from '@/shared/ui/data/EmptyState'
import { LayoutGrid } from '@/shared/ui/icons'

export function PipelinePage() {
  return (
    <>
      <PageHeader
        title="Pipeline"
        description="Acompanhe oportunidades de prospecção em estágios"
      />
      <EmptyState
        icon={LayoutGrid}
        title="Pipeline vazio"
        description="Mova empresas da prospecção ou de uma lista para este pipeline."
      />
    </>
  )
}
