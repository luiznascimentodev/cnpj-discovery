import { describe, expect, it } from 'vitest'
import { render, screen } from '@testing-library/react'
import { axe } from 'vitest-axe'
import { FormField } from './FormField'
import { Input } from '../Input/Input'

describe('FormField', () => {
  it('associa label, helper e erro', async () => {
    const { container } = render(
      <FormField label="Nome" helper="Como aparece em relatórios" error="Obrigatório">
        <Input aria-label="Nome" />
      </FormField>
    )
    expect(screen.getByText('Nome')).toBeInTheDocument()
    expect(screen.getByText('Obrigatório')).toBeInTheDocument()
    expect(await axe(container)).toHaveNoViolations()
  })
  it('mostra helper quando não há erro', () => {
    render(
      <FormField label="X" helper="ajuda">
        <Input aria-label="x" />
      </FormField>
    )
    expect(screen.getByText('ajuda')).toBeInTheDocument()
  })
})
