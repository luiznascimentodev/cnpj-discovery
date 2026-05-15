import { describe, expect, it } from 'vitest'
import { render, screen } from '@testing-library/react'
import { MemoryRouter } from 'react-router'
import { axe } from 'vitest-axe'
import { LandingPage } from './LandingPage'

function renderLanding() {
  return render(
    <MemoryRouter>
      <LandingPage />
    </MemoryRouter>
  )
}

describe('LandingPage', () => {
  it('renderiza o hero, features e CTA de fechamento', () => {
    renderLanding()
    expect(
      screen.getByRole('heading', { level: 1, name: /prospecção b2b/i })
    ).toBeInTheDocument()
    expect(
      screen.getByRole('heading', { level: 2, name: /tudo que você precisa/i })
    ).toBeInTheDocument()
    expect(
      screen.getByRole('heading', { level: 2, name: /parar de prospectar no escuro/i })
    ).toBeInTheDocument()
    expect(screen.getAllByRole('article')).toHaveLength(3)
  })

  it('CTAs principais apontam para registro e login', () => {
    renderLanding()
    const ctaPrimario = screen.getByRole('link', { name: /começar gratuitamente/i })
    expect(ctaPrimario).toHaveAttribute('href', '/registro')
    const ctaSecundario = screen.getByRole('link', { name: /já tenho conta/i })
    expect(ctaSecundario).toHaveAttribute('href', '/login')
    const ctaFechamento = screen.getByRole('link', { name: /criar conta grátis/i })
    expect(ctaFechamento).toHaveAttribute('href', '/registro')
  })

  it('header tem links de entrar e criar conta', () => {
    renderLanding()
    expect(screen.getByRole('link', { name: /^entrar$/i })).toHaveAttribute('href', '/login')
    expect(screen.getByRole('link', { name: /^criar conta$/i })).toHaveAttribute('href', '/registro')
  })

  it('passa axe sem violações', async () => {
    const { container } = renderLanding()
    expect(await axe(container)).toHaveNoViolations()
  })
})
