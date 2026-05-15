import { describe, expect, it } from 'vitest'
import { render, screen } from '@testing-library/react'
import { PageHeader } from './PageHeader'

describe('PageHeader', () => {
  it('renderiza título, descrição, breadcrumb e ações', () => {
    render(
      <PageHeader
        title="Empresas ativas"
        description="2.345 resultados"
        breadcrumb={<span>Início / Prospecção</span>}
        actions={<button type="button">Exportar</button>}
      />
    )
    expect(screen.getByRole('heading', { level: 1, name: 'Empresas ativas' })).toBeInTheDocument()
    expect(screen.getByText('2.345 resultados')).toBeInTheDocument()
    expect(screen.getByText('Início / Prospecção')).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Exportar' })).toBeInTheDocument()
  })
})
