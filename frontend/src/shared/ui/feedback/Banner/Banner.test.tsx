import { describe, expect, it, vi } from 'vitest'
import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { Banner } from './Banner'

describe('Banner', () => {
  it('chama onDismiss ao clicar em fechar', async () => {
    const onDismiss = vi.fn()
    render(
      <Banner tone="info" onDismiss={onDismiss}>
        Nova versão disponível.
      </Banner>
    )
    await userEvent.click(screen.getByLabelText('Fechar'))
    expect(onDismiss).toHaveBeenCalledOnce()
  })
})
