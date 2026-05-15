import { describe, expect, it } from 'vitest'
import { render, screen } from '@testing-library/react'
import { MemoryRouter, Route, Routes } from 'react-router'
import { AppShell } from './AppShell'

describe('AppShell', () => {
  it('renderiza SideNav, TopBar e área principal com landmark', () => {
    render(
      <MemoryRouter initialEntries={['/app/prospeccao']}>
        <Routes>
          <Route element={<AppShell user={{ id: '1', name: 'Ana Lima', email: 'a@b.c' }} />}>
            <Route path="/app/prospeccao" element={<p>Conteúdo</p>} />
          </Route>
        </Routes>
      </MemoryRouter>
    )
    expect(screen.getByRole('navigation', { name: 'Navegação principal' })).toBeInTheDocument()
    expect(screen.getByRole('main')).toBeInTheDocument()
    expect(screen.getByText('Conteúdo')).toBeInTheDocument()
    expect(screen.getByText('AL')).toBeInTheDocument()
  })

  it('marca link da rota ativa', () => {
    render(
      <MemoryRouter initialEntries={['/app/pipeline']}>
        <Routes>
          <Route element={<AppShell />}>
            <Route path="/app/pipeline" element={<p>x</p>} />
          </Route>
        </Routes>
      </MemoryRouter>
    )
    const activeLink = screen.getByRole('link', { name: /Pipeline/ })
    expect(activeLink).toHaveAttribute('aria-current', 'page')
  })
})
