import { describe, expect, it, vi } from 'vitest'
import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { ConfirmDialog } from './ConfirmDialog'

describe('ConfirmDialog', () => {
  it('chama onConfirm e fecha ao confirmar', async () => {
    const onConfirm = vi.fn()
    const onOpenChange = vi.fn()
    render(
      <ConfirmDialog
        open
        onOpenChange={onOpenChange}
        title="Remover lista?"
        description="Esta ação não pode ser desfeita."
        tone="danger"
        confirmLabel="Remover"
        onConfirm={onConfirm}
      />
    )
    expect(screen.getByText('Remover lista?')).toBeInTheDocument()
    await userEvent.click(screen.getByRole('button', { name: 'Remover' }))
    expect(onConfirm).toHaveBeenCalledOnce()
  })
})
