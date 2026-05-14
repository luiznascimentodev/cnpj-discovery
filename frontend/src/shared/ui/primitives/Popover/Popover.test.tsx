import { describe, expect, it } from 'vitest'
import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { PopoverRoot, PopoverTrigger, PopoverContent } from './Popover'

describe('Popover', () => {
  it('abre ao clicar no trigger', async () => {
    render(
      <PopoverRoot>
        <PopoverTrigger>abrir</PopoverTrigger>
        <PopoverContent>conteúdo</PopoverContent>
      </PopoverRoot>
    )
    await userEvent.click(screen.getByText('abrir'))
    expect(await screen.findByText('conteúdo')).toBeInTheDocument()
  })
})
