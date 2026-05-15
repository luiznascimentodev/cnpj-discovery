import { PageHeader } from '@/shared/ui/layout/PageHeader'
import { EmptyState } from '@/shared/ui/data/EmptyState'
import { Bookmark } from '@/shared/ui/icons'

export function ListasPage() {
  return (
    <>
      <PageHeader title="Listas salvas" description="Suas listas de empresas favoritadas" />
      <EmptyState
        icon={Bookmark}
        title="Nenhuma lista salva"
        description="Salve listas a partir da prospecção para acessá-las depois."
      />
    </>
  )
}
