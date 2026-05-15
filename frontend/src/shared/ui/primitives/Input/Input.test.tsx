import { describe, expect, it } from 'vitest'
import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { axe } from 'vitest-axe'
import { Input } from './Input'

describe('Input', () => {
  it('aceita digitação', async () => {
    render(<Input aria-label="nome" />)
    await userEvent.type(screen.getByLabelText('nome'), 'abc')
    expect(screen.getByLabelText('nome')).toHaveValue('abc')
  })
  it('marca aria-invalid quando invalid', () => {
    render(<Input aria-label="x" invalid />)
    expect(screen.getByLabelText('x')).toHaveAttribute('aria-invalid', 'true')
  })
  it('passa axe', async () => {
    const { container } = render(<Input aria-label="x" />)
    expect(await axe(container)).toHaveNoViolations()
  })
})
