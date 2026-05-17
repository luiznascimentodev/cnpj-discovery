import { useState } from 'react'
import { Button, DialogContent, DialogDescription, DialogRoot, DialogTitle, SelectContent, SelectItem, SelectRoot, SelectTrigger, SelectValue } from '@/shared/ui'
import { FileUp } from '@/shared/ui/icons'
import type { ImportResult, StageRecord } from '../schemas'

interface ImportCsvDialogProps {
  open: boolean
  onOpenChange: (open: boolean) => void
  stages: StageRecord[]
  result: ImportResult | null
  onSubmit: (payload: { stageId: string; file: File }) => void
  loading: boolean
}

export function ImportCsvDialog({ open, onOpenChange, stages, result, onSubmit, loading }: ImportCsvDialogProps) {
  const [stageId, setStageId] = useState(stages[0]?.id ?? '')
  const [textCsv, setTextCsv] = useState('')

  return (
    <DialogRoot open={open} onOpenChange={onOpenChange}>
      <DialogContent size="lg">
        <DialogTitle>Importar CSV</DialogTitle>
        <DialogDescription>O arquivo será salvo com histórico por linha e vinculado aos CNPJs quando possível.</DialogDescription>
        <form
          className="mt-5 space-y-4"
          onSubmit={(event) => {
            event.preventDefault()
            const data = new FormData(event.currentTarget)
            const file = data.get('file')
            const targetStageId = stageId || stages[0]?.id
            if (!targetStageId) return
            if (file instanceof File && file.size > 0) {
              onSubmit({ stageId: targetStageId, file })
              return
            }
            if (textCsv.trim()) {
              onSubmit({
                stageId: targetStageId,
                file: new File([textCsv], `colado-${Date.now()}.csv`, { type: 'text/csv' }),
              })
            }
          }}
        >
          <SelectRoot value={stageId || stages[0]?.id} onValueChange={setStageId}>
            <SelectTrigger aria-label="Estágio destino">
              <SelectValue placeholder="Estágio destino" />
            </SelectTrigger>
            <SelectContent>
              {stages.map((stage) => <SelectItem key={stage.id} value={stage.id}>{stage.name}</SelectItem>)}
            </SelectContent>
          </SelectRoot>
          <label className="flex cursor-pointer flex-col items-center justify-center rounded-md border border-dashed border-[var(--color-border-strong)] bg-[var(--color-bg-subtle)] p-6 text-center">
            <FileUp size={24} aria-hidden="true" />
            <span className="mt-2 text-[var(--text-sm)] font-medium">Selecionar arquivo CSV</span>
            <input className="sr-only" name="file" type="file" accept=".csv,text/csv" />
          </label>
          <textarea
            className="min-h-32 w-full rounded-md border border-[var(--color-border-strong)] bg-[var(--color-bg-surface)] p-3 text-[var(--text-sm)]"
            value={textCsv}
            onChange={(event) => setTextCsv(event.target.value)}
            placeholder="Ou cole o CSV aqui"
          />
          {result && (
            <div className="rounded-md border border-[var(--color-border)] bg-[var(--color-bg-subtle)] p-3 text-[var(--text-sm)]">
              <p className="font-semibold">Import {result.batch.id}</p>
              <p>Total: {result.summary.total_rows} · Criados: {result.created} · Ignorados: {result.skipped.length}</p>
              {result.skipped.length > 0 && (
                <ul className="mt-2 max-h-28 overflow-auto text-[var(--text-xs)] text-[var(--color-fg-secondary)]">
                  {result.skipped.slice(0, 20).map((row) => (
                    <li key={`${row.line}-${row.cnpj}`}>linha {row.line}: {row.cnpj || '-'} · {row.reason}</li>
                  ))}
                </ul>
              )}
            </div>
          )}
          <div className="flex justify-end gap-2">
            <Button type="button" variant="secondary" onClick={() => onOpenChange(false)}>Fechar</Button>
            <Button type="submit" loading={loading}>Importar</Button>
          </div>
        </form>
      </DialogContent>
    </DialogRoot>
  )
}
