import { type ReactNode } from 'react'
import {
  AlertDialogRoot,
  AlertDialogContent,
  AlertDialogTitle,
  AlertDialogDescription,
  AlertDialogAction,
  AlertDialogCancel,
} from '@/shared/ui/primitives/AlertDialog'
import { Button } from '@/shared/ui/primitives/Button'

export interface ConfirmDialogProps {
  open: boolean
  onOpenChange: (open: boolean) => void
  title: ReactNode
  description?: ReactNode
  confirmLabel?: string
  cancelLabel?: string
  tone?: 'default' | 'danger'
  onConfirm: () => void
}

export function ConfirmDialog({
  open,
  onOpenChange,
  title,
  description,
  confirmLabel = 'Confirmar',
  cancelLabel = 'Cancelar',
  tone = 'default',
  onConfirm,
}: ConfirmDialogProps) {
  return (
    <AlertDialogRoot open={open} onOpenChange={onOpenChange}>
      <AlertDialogContent>
        <AlertDialogTitle className="text-[var(--text-lg)] font-semibold text-[var(--color-fg-primary)]">
          {title}
        </AlertDialogTitle>
        {description && (
          <AlertDialogDescription className="mt-2 text-[var(--text-sm)] text-[var(--color-fg-muted)]">
            {description}
          </AlertDialogDescription>
        )}
        <div className="mt-6 flex justify-end gap-2">
          <AlertDialogCancel asChild>
            <Button variant="ghost">{cancelLabel}</Button>
          </AlertDialogCancel>
          <AlertDialogAction asChild>
            <Button variant={tone === 'danger' ? 'danger' : 'primary'} onClick={onConfirm}>
              {confirmLabel}
            </Button>
          </AlertDialogAction>
        </div>
      </AlertDialogContent>
    </AlertDialogRoot>
  )
}
