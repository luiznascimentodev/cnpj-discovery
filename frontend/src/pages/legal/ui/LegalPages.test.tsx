import { describe, expect, it } from 'vitest'
import { render, screen } from '@testing-library/react'
import { MemoryRouter } from 'react-router'
import { axe } from 'vitest-axe'
import { TermosPage } from './TermosPage'
import { PrivacidadePage } from './PrivacidadePage'

function wrap(node: React.ReactNode) {
  return <MemoryRouter>{node}</MemoryRouter>
}

describe('TermosPage', () => {
  it('renderiza título e seções principais', () => {
    render(wrap(<TermosPage />))
    expect(screen.getByRole('heading', { level: 1, name: /termos de uso/i })).toBeInTheDocument()
    expect(screen.getByRole('heading', { name: /^1\. objeto$/i })).toBeInTheDocument()
    expect(screen.getByRole('heading', { name: /lei aplicável/i })).toBeInTheDocument()
  })

  it('passa axe', async () => {
    const { container } = render(wrap(<TermosPage />))
    expect(await axe(container)).toHaveNoViolations()
  })
})

describe('PrivacidadePage', () => {
  it('renderiza título e seções LGPD essenciais', () => {
    render(wrap(<PrivacidadePage />))
    expect(
      screen.getByRole('heading', { level: 1, name: /política de privacidade/i })
    ).toBeInTheDocument()
    expect(screen.getByRole('heading', { name: /controlador/i })).toBeInTheDocument()
    expect(screen.getByRole('heading', { name: /direitos do titular/i })).toBeInTheDocument()
    expect(screen.getByRole('heading', { name: /retenção/i })).toBeInTheDocument()
  })

  it('passa axe', async () => {
    const { container } = render(wrap(<PrivacidadePage />))
    expect(await axe(container)).toHaveNoViolations()
  })
})
