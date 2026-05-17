import { Button, DialogContent, DialogDescription, DialogRoot, DialogTitle, Input, SelectContent, SelectItem, SelectRoot, SelectTrigger, SelectValue, Textarea } from '@/shared/ui'
import type { StageRecord } from '../schemas'

interface CreateCardDialogProps {
  open: boolean
  onOpenChange: (open: boolean) => void
  stages: StageRecord[]
  onSubmit: (payload: { cnpj_basico: string; stage_id: string | null; display_name: string | null; notes: string | null }) => void
  loading: boolean
}

export function CreateCardDialog({ open, onOpenChange, stages, onSubmit, loading }: CreateCardDialogProps) {
  return (
    <DialogRoot open={open} onOpenChange={onOpenChange}>
      <DialogContent>
        <DialogTitle>Novo card</DialogTitle>
        <DialogDescription>Digite o CNPJ básico e, se quiser, um nome interno para o card.</DialogDescription>
        <form
          className="mt-5 space-y-4"
          onSubmit={(event) => {
            event.preventDefault()
            const data = new FormData(event.currentTarget)
            const cnpj = String(data.get('cnpj_basico') ?? '').replace(/\D/g, '').slice(0, 8)
            const displayName = String(data.get('display_name') ?? '').trim()
            const notes = String(data.get('notes') ?? '').trim()
            const stageId = String(data.get('stage_id') ?? '')
            if (cnpj.length !== 8) return
            onSubmit({
              cnpj_basico: cnpj,
              stage_id: stageId || null,
              display_name: displayName || null,
              notes: notes || null,
            })
          }}
        >
          <Input name="cnpj_basico" inputMode="numeric" placeholder="CNPJ básico: 12345678" required maxLength={18} />
          <Input name="display_name" placeholder="Nome do card" maxLength={200} />
          <SelectRoot name="stage_id" defaultValue={stages[0]?.id}>
            <SelectTrigger aria-label="Estágio">
              <SelectValue placeholder="Estágio" />
            </SelectTrigger>
            <SelectContent>
              {stages.map((stage) => <SelectItem key={stage.id} value={stage.id}>{stage.name}</SelectItem>)}
            </SelectContent>
          </SelectRoot>
          <Textarea name="notes" placeholder="Notas" maxLength={10000} />
          <div className="flex justify-end gap-2">
            <Button type="button" variant="secondary" onClick={() => onOpenChange(false)}>Cancelar</Button>
            <Button type="submit" loading={loading}>Criar card</Button>
          </div>
        </form>
      </DialogContent>
    </DialogRoot>
  )
}
