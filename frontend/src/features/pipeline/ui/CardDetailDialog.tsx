import { Button, DialogContent, DialogDescription, DialogRoot, DialogTitle, Input, SelectContent, SelectItem, SelectRoot, SelectTrigger, SelectValue, Textarea } from '@/shared/ui'
import { CheckSquare, MessageSquare, Phone, Mail, Calendar, Square } from '@/shared/ui/icons'
import { formatCurrency, formatDate } from '@/shared/lib'
import { useCardDetail, useCardDetailMutations } from '../hooks'
import { cardLabel } from '../model/board'
import type { ActivityKind, CardWithCompany, StageRecord } from '../schemas'

interface CardDetailDialogProps {
  open: boolean
  onOpenChange: (open: boolean) => void
  pipelineId: string
  stages: StageRecord[]
  item: CardWithCompany | null
  onUpdate: (cardId: string, payload: { display_name?: string | null; estimated_value_cents?: number | null; notes?: string | null }) => void
  onMove: (cardId: string, stageId: string) => void
  updating: boolean
}

const activityIcon: Record<ActivityKind, typeof MessageSquare> = {
  note: MessageSquare,
  call: Phone,
  email: Mail,
  meeting: Calendar,
}

export function CardDetailDialog({
  open,
  onOpenChange,
  pipelineId,
  stages,
  item,
  onUpdate,
  onMove,
  updating,
}: CardDetailDialogProps) {
  const cardId = item?.card.id ?? null
  const detail = useCardDetail(pipelineId, cardId)
  const mutations = useCardDetailMutations(pipelineId, cardId ?? '')

  if (!item) return null

  return (
    <DialogRoot open={open} onOpenChange={onOpenChange}>
      <DialogContent size="xl" className="max-h-[90vh] overflow-y-auto">
        <DialogTitle>{cardLabel(item)}</DialogTitle>
        <DialogDescription>
          {item.card.cnpj_basico}{item.company.razao_social ? ` · ${item.company.razao_social}` : ''}
        </DialogDescription>

        <div className="mt-5 grid gap-5 lg:grid-cols-[1fr_320px]">
          <div className="space-y-5">
            <section className="space-y-3">
              <form
                key={item.card.id}
                className="space-y-3"
                onSubmit={(event) => {
                  event.preventDefault()
                  const data = new FormData(event.currentTarget)
                  const displayName = String(data.get('display_name') ?? '').trim()
                  const estimatedValue = String(data.get('estimated_value') ?? '').trim()
                  const notes = String(data.get('notes') ?? '').trim()
                  onUpdate(item.card.id, {
                    display_name: displayName || null,
                    estimated_value_cents: estimatedValue ? Math.round(Number(estimatedValue.replace(',', '.')) * 100) : null,
                    notes: notes || null,
                  })
                }}
              >
                <div className="grid gap-3 sm:grid-cols-2">
                  <Input name="display_name" defaultValue={item.card.display_name ?? ''} placeholder="Nome do card" />
                  <Input
                    name="estimated_value"
                    defaultValue={item.card.estimated_value_cents ? String(item.card.estimated_value_cents / 100) : ''}
                    inputMode="decimal"
                    placeholder="Valor estimado"
                  />
                </div>
                <Textarea name="notes" defaultValue={item.card.notes ?? ''} placeholder="Notas" rows={5} />
                <div className="flex flex-wrap justify-between gap-2">
                  <SelectRoot value={item.card.stage_id} onValueChange={(stageId) => onMove(item.card.id, stageId)}>
                    <SelectTrigger className="w-64 max-w-full" aria-label="Mover para estágio">
                      <SelectValue />
                    </SelectTrigger>
                    <SelectContent>
                      {stages.map((stage) => <SelectItem key={stage.id} value={stage.id}>{stage.name}</SelectItem>)}
                    </SelectContent>
                  </SelectRoot>
                  <Button type="submit" loading={updating}>Salvar</Button>
                </div>
              </form>
            </section>

            <section>
              <h3 className="text-[var(--text-sm)] font-semibold">Dados importados do CSV</h3>
              <div className="mt-2 space-y-2">
                {(detail.importRows.data ?? []).length === 0 && (
                  <p className="text-[var(--text-sm)] text-[var(--color-fg-secondary)]">Sem dados importados para este card.</p>
                )}
                {(detail.importRows.data ?? []).map((row) => (
                  <div key={row.id} className="rounded-md border border-[var(--color-border)] p-3">
                    <p className="text-[var(--text-xs)] text-[var(--color-fg-secondary)]">
                      linha {row.line_number} · {row.status}{row.reason ? ` · ${row.reason}` : ''}
                    </p>
                    <dl className="mt-2 grid gap-2 sm:grid-cols-2">
                      {Object.entries(row.metadata).map(([key, value]) => (
                        <div key={key} className="min-w-0">
                          <dt className="truncate text-[var(--text-xs)] font-medium text-[var(--color-fg-secondary)]">{key}</dt>
                          <dd className="break-words text-[var(--text-sm)]">{String(value)}</dd>
                        </div>
                      ))}
                    </dl>
                  </div>
                ))}
              </div>
            </section>

            <section>
              <h3 className="text-[var(--text-sm)] font-semibold">Atividades</h3>
              <form
                className="mt-2 flex gap-2"
                onSubmit={(event) => {
                  event.preventDefault()
                  const data = new FormData(event.currentTarget)
                  const body = String(data.get('body') ?? '').trim()
                  if (!body || !cardId) return
                  mutations.createActivity.mutate({ kind: 'note', body })
                  event.currentTarget.reset()
                }}
              >
                <Input name="body" placeholder="Registrar nota" />
                <Button type="submit" variant="secondary">Adicionar</Button>
              </form>
              <div className="mt-3 space-y-2">
                {(detail.activities.data ?? []).map((activity) => {
                  const Icon = activityIcon[activity.kind]
                  return (
                    <div key={activity.id} className="rounded-md border border-[var(--color-border)] p-3">
                      <p className="flex items-center gap-2 text-[var(--text-xs)] text-[var(--color-fg-secondary)]">
                        <Icon size={14} aria-hidden="true" /> {activity.kind} · {formatDate(activity.occurred_at)}
                      </p>
                      <p className="mt-1 text-[var(--text-sm)]">{activity.body}</p>
                    </div>
                  )
                })}
              </div>
            </section>
          </div>

          <aside className="space-y-4">
            <div className="rounded-md border border-[var(--color-border)] p-3">
              <p className="text-[var(--text-xs)] text-[var(--color-fg-secondary)]">Valor</p>
              <p className="text-[var(--text-md)] font-semibold">
                {item.card.estimated_value_cents === null ? '-' : formatCurrency(item.card.estimated_value_cents)}
              </p>
            </div>

            <section>
              <h3 className="text-[var(--text-sm)] font-semibold">Tasks</h3>
              <form
                className="mt-2 flex gap-2"
                onSubmit={(event) => {
                  event.preventDefault()
                  const data = new FormData(event.currentTarget)
                  const title = String(data.get('title') ?? '').trim()
                  if (!title || !cardId) return
                  mutations.createTask.mutate({ title })
                  event.currentTarget.reset()
                }}
              >
                <Input name="title" size="sm" placeholder="Nova task" />
                <Button size="sm" type="submit">Criar</Button>
              </form>
              <div className="mt-3 space-y-2">
                {(detail.tasks.data ?? []).map((task) => {
                  const done = Boolean(task.done_at)
                  return (
                    <button
                      key={task.id}
                      type="button"
                      className="flex w-full items-start gap-2 rounded-md border border-[var(--color-border)] p-2 text-left text-[var(--text-sm)] hover:bg-[var(--color-bg-subtle)]"
                      onClick={() => mutations.updateTask.mutate({ taskId: task.id, done_at: done ? null : new Date().toISOString() })}
                    >
                      {done ? <CheckSquare size={16} aria-hidden="true" /> : <Square size={16} aria-hidden="true" />}
                      <span className={done ? 'line-through text-[var(--color-fg-secondary)]' : ''}>{task.title}</span>
                    </button>
                  )
                })}
              </div>
            </section>
          </aside>
        </div>
      </DialogContent>
    </DialogRoot>
  )
}
