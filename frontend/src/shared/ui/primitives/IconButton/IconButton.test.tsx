import { describe, expect, it } from 'vitest'
import { render, screen } from '@testing-library/react'
import { axe } from 'vitest-axe'
import { IconButton } from './IconButton'
import { Plus } from '@/shared/ui/icons'

describe('IconButton', () => {
  it('renderiza com aria-label e ícone', async () => {
    const { container } = render(
      <IconButton aria-label="Adicionar"><Plus size={16} aria-hidden="true" /></IconButton>
    )
    expect(screen.getByRole('button', { name: 'Adicionar' })).toBeInTheDocument()
    expect(await axe(container)).toHaveNoViolations()
  })
})
