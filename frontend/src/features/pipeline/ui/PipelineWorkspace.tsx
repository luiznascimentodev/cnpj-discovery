import { useMemo, useState } from 'react'
import { PageHeader } from '@/shared/ui/layout/PageHeader'
import { EmptyState } from '@/shared/ui/data/EmptyState'
import { Button, SelectContent, SelectItem, SelectRoot, SelectTrigger, SelectValue } from '@/shared/ui'
import { LayoutGrid, Plus, Upload } from '@/shared/ui/icons'
import { usePipelineData, usePipelineMutations, usePipelines } from '../hooks'
import type { CardWithCompany } from '../schemas'
import { PipelineBoard } from './PipelineBoard'
import { CreatePipelineDialog } from './CreatePipelineDialog'
import { CreateCardDialog } from './CreateCardDialog'
import { ImportCsvDialog } from './ImportCsvDialog'
import { CardDetailDialog } from './CardDetailDialog'

export function PipelineWorkspace() {
  const [selectedPipelineId, setSelectedPipelineId] = useState<string | null>(null)
  const [createPipelineOpen, setCreatePipelineOpen] = useState(false)
  const [createCardOpen, setCreateCardOpen] = useState(false)
  const [importOpen, setImportOpen] = useState(false)
  const [selectedCard, setSelectedCard] = useState<CardWithCompany | null>(null)

  const pipelines = usePipelines()
  const activePipelineId = selectedPipelineId ?? pipelines.data?.[0]?.id ?? null
  const activePipeline = useMemo(
    () => pipelines.data?.find((pipeline) => pipeline.id === activePipelineId) ?? null,
    [activePipelineId, pipelines.data],
  )
  const { stages, cards } = usePipelineData(activePipelineId)
  const mutations = usePipelineMutations(activePipelineId)

  const loading = pipelines.isLoading || stages.isLoading || cards.isLoading
  const hasPipeline = Boolean(activePipelineId)

  return (
    <div className="flex min-h-[calc(100vh-96px)] flex-col gap-4">
      <PageHeader
        title="Pipeline"
        description="Organize oportunidades, tarefas e dados importados por estágio."
        actions={(
          <div className="flex flex-wrap items-center gap-2">
            {hasPipeline && (
              <>
                <Button variant="secondary" onClick={() => setImportOpen(true)}>
                  <Upload size={16} aria-hidden="true" /> Importar CSV
                </Button>
                <Button onClick={() => setCreateCardOpen(true)}>
                  <Plus size={16} aria-hidden="true" /> Card
                </Button>
              </>
            )}
            <Button variant={hasPipeline ? 'secondary' : 'primary'} onClick={() => setCreatePipelineOpen(true)}>
              <Plus size={16} aria-hidden="true" /> Pipeline
            </Button>
          </div>
        )}
      />

      {pipelines.data && pipelines.data.length > 0 && (
        <div className="flex flex-wrap items-center gap-3 rounded-md border border-[var(--color-border)] bg-[var(--color-bg-surface)] p-3">
          <div className="w-72 max-w-full">
            <SelectRoot value={activePipelineId ?? undefined} onValueChange={setSelectedPipelineId}>
              <SelectTrigger aria-label="Pipeline ativo">
                <SelectValue placeholder="Selecione um pipeline" />
              </SelectTrigger>
              <SelectContent>
                {pipelines.data.map((pipeline) => (
                  <SelectItem key={pipeline.id} value={pipeline.id}>{pipeline.name}</SelectItem>
                ))}
              </SelectContent>
            </SelectRoot>
          </div>
          {activePipeline && (
            <span className="text-[var(--text-sm)] text-[var(--color-fg-secondary)]">
              {cards.data?.length ?? 0} cards em {stages.data?.length ?? 0} estágios
            </span>
          )}
        </div>
      )}

      {!loading && !hasPipeline && (
        <EmptyState
          icon={LayoutGrid}
          title="Nenhum pipeline criado"
          description="Crie um pipeline para organizar cards por estágio."
          action={<Button onClick={() => setCreatePipelineOpen(true)}>Criar pipeline</Button>}
        />
      )}

      {hasPipeline && (
        <PipelineBoard
          pipelineId={activePipelineId as string}
          stages={stages.data ?? []}
          cards={cards.data ?? []}
          loading={loading}
          onOpenCard={setSelectedCard}
          onCreateStage={(name) => mutations.createStage.mutate({ name })}
          onMoveCard={(cardId, stageId, position) => mutations.moveCard.mutate({ cardId, stageId, position })}
          onReorderStages={(stageIds) => mutations.reorderStages.mutate(stageIds)}
        />
      )}

      <CreatePipelineDialog
        open={createPipelineOpen}
        onOpenChange={setCreatePipelineOpen}
        onSubmit={(payload) => mutations.createPipeline.mutate(payload, { onSuccess: (pipeline) => setSelectedPipelineId(pipeline.id) })}
        loading={mutations.createPipeline.isPending}
      />
      {activePipelineId && (
        <>
          <CreateCardDialog
            open={createCardOpen}
            onOpenChange={setCreateCardOpen}
            stages={stages.data ?? []}
            onSubmit={(payload) => mutations.createCard.mutate(payload, { onSuccess: () => setCreateCardOpen(false) })}
            loading={mutations.createCard.isPending}
          />
          <ImportCsvDialog
            open={importOpen}
            onOpenChange={setImportOpen}
            stages={stages.data ?? []}
            result={mutations.importCards.data ?? null}
            onSubmit={(payload) => mutations.importCards.mutate(payload)}
            loading={mutations.importCards.isPending}
          />
          <CardDetailDialog
            open={Boolean(selectedCard)}
            onOpenChange={(open) => !open && setSelectedCard(null)}
            pipelineId={activePipelineId}
            stages={stages.data ?? []}
            item={selectedCard}
            onUpdate={(cardId, payload) => mutations.updateCard.mutate({ cardId, payload })}
            onMove={(cardId, stageId) => mutations.moveCard.mutate({ cardId, stageId, position: 0 })}
            updating={mutations.updateCard.isPending || mutations.moveCard.isPending}
          />
        </>
      )}
    </div>
  )
}
