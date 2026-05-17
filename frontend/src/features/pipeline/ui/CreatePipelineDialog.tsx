import { Button, DialogContent, DialogDescription, DialogRoot, DialogTitle, Input, Textarea } from '@/shared/ui'

interface CreatePipelineDialogProps {
  open: boolean
  onOpenChange: (open: boolean) => void
  onSubmit: (payload: { name: string; description: string | null }) => void
  loading: boolean
}

export function CreatePipelineDialog({ open, onOpenChange, onSubmit, loading }: CreatePipelineDialogProps) {
  return (
    <DialogRoot open={open} onOpenChange={onOpenChange}>
      <DialogContent>
        <DialogTitle>Novo pipeline</DialogTitle>
        <DialogDescription>Crie um funil de trabalho para seus cards.</DialogDescription>
        <form
          className="mt-5 space-y-4"
          onSubmit={(event) => {
            event.preventDefault()
            const data = new FormData(event.currentTarget)
            const name = String(data.get('name') ?? '').trim()
            const description = String(data.get('description') ?? '').trim()
            if (!name) return
            onSubmit({ name, description: description || null })
            event.currentTarget.reset()
          }}
        >
          <Input name="name" placeholder="Nome do pipeline" required maxLength={120} />
          <Textarea name="description" placeholder="Descrição" maxLength={2000} />
          <div className="flex justify-end gap-2">
            <Button type="button" variant="secondary" onClick={() => onOpenChange(false)}>Cancelar</Button>
            <Button type="submit" loading={loading}>Criar</Button>
          </div>
        </form>
      </DialogContent>
    </DialogRoot>
  )
}
