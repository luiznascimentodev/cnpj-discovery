import { describe, expect, it } from 'vitest'
import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { DialogRoot, DialogTrigger, DialogContent, DialogTitle } from './Dialog'

describe('Dialog', () => {
  it('abre, e fecha via Esc', async () => {
    render(
      <DialogRoot>
        <DialogTrigger>abrir</DialogTrigger>
        <DialogContent>
          <DialogTitle>Título</DialogTitle>
        </DialogContent>
      </DialogRoot>
    )
    await userEvent.click(screen.getByText('abrir'))
    expect(await screen.findByText('Título')).toBeInTheDocument()
    await userEvent.keyboard('{Escape}')
    expect(screen.queryByText('Título')).not.toBeInTheDocument()
  })
})
