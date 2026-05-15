import { describe, expect, it } from 'vitest'
import { render, screen } from '@testing-library/react'
import { Alert } from './Alert'

describe('Alert', () => {
  it('possui role alert e exibe título e descrição', () => {
    render(
      <Alert tone="warning" title="Atenção">
        Confira os dados antes de prosseguir.
      </Alert>
    )
    const el = screen.getByRole('alert')
    expect(el).toHaveTextContent('Atenção')
    expect(el).toHaveTextContent('Confira os dados antes de prosseguir.')
  })
})
