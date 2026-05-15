import { describe, expect, it } from 'vitest'
import { render, screen } from '@testing-library/react'
import { Stat } from './Stat'

describe('Stat', () => {
  it('renderiza label, value e delta', () => {
    render(<Stat label="Empresas" value="1.247.832" delta={{ value: '+12%', positive: true }} />)
    expect(screen.getByText('Empresas')).toBeInTheDocument()
    expect(screen.getByText('1.247.832')).toBeInTheDocument()
    expect(screen.getByText('+12%')).toBeInTheDocument()
  })
})
