import { describe, expect, it } from 'vitest'
import { render, screen } from '@testing-library/react'
import { Spinner } from './Spinner'

describe('Spinner', () => {
  it('expõe role=status e aria-label', () => {
    render(<Spinner />)
    expect(screen.getByRole('status', { name: 'Carregando' })).toBeInTheDocument()
  })
})
