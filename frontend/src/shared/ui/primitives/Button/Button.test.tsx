import { describe, expect, it, vi } from 'vitest'
import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { axe } from 'vitest-axe'
import { Button } from './Button'

describe('Button', () => {
  it('renderiza o texto', () => {
    render(<Button>Salvar</Button>)
    expect(screen.getByRole('button', { name: 'Salvar' })).toBeInTheDocument()
  })
  it('dispara onClick', async () => {
    const onClick = vi.fn()
    render(<Button onClick={onClick}>Salvar</Button>)
    await userEvent.click(screen.getByRole('button'))
    expect(onClick).toHaveBeenCalledOnce()
  })
  it('mostra estado loading e desabilita', () => {
    render(<Button loading>Salvar</Button>)
    expect(screen.getByRole('button')).toBeDisabled()
    expect(screen.getByRole('button')).toHaveAttribute('aria-busy', 'true')
  })
  it('passa axe', async () => {
    const { container } = render(<Button>Salvar</Button>)
    expect(await axe(container)).toHaveNoViolations()
  })
})
