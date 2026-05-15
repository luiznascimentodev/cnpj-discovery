import { describe, expect, it } from 'vitest'
import { render, screen } from '@testing-library/react'
import { Badge } from './Badge'

describe('Badge', () => {
  it('renderiza conteúdo com variant', () => {
    render(<Badge variant="success">Ativa</Badge>)
    expect(screen.getByText('Ativa')).toBeInTheDocument()
  })
})
