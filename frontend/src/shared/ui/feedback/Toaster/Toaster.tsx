import { Toaster as SonnerToaster } from 'sonner'

export function Toaster() {
  return (
    <SonnerToaster
      position="bottom-right"
      richColors
      closeButton
      toastOptions={{
        classNames: {
          toast:
            'rounded-lg border border-[var(--color-border)] bg-[var(--color-bg-surface)] text-[var(--color-fg-primary)] shadow-md',
          description: 'text-[var(--color-fg-muted)]',
        },
      }}
    />
  )
}
